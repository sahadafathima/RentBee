from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from catalog.models import Item
from catalog.serializers import ItemImageSerializer
from .models import Booking, IssueReport, AvailabilityNotificationRequest, InAppNotification
from .services import get_item_availability, notify_booking_event


class IssueReportSerializer(serializers.ModelSerializer):
    renter_name = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()

    class Meta:
        model = IssueReport
        fields = [
            'id', 'booking', 'renter', 'renter_name',
            'owner', 'owner_name', 'description', 'status',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'booking', 'renter', 'owner', 'status', 'created_at', 'updated_at']

    def get_renter_name(self, obj):
        return getattr(obj.renter, 'full_name', '') or 'Renter'

    def get_owner_name(self, obj):
        return getattr(obj.owner, 'full_name', '') or 'Host'

    def validate_description(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Problem description cannot be empty.")
        return cleaned


class BookingItemSummarySerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    primary_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = ['id', 'name', 'category_name', 'primary_image_url', 'rental_price', 'deposit']

    def get_primary_image_url(self, obj):
        images = list(obj.images.all())
        if not images:
            return None
        img = next((i for i in images if i.is_primary), images[0])
        if not img or not img.image:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(img.image.url)
        return img.image.url


class BookingParticipantPrivacyMixin:
    CONTACT_STATUSES = {'waiting_for_pickup', 'rental_in_progress', 'completed'}

    def participant_data(self, booking, participant, role):
        request = self.context.get('request')
        viewer = getattr(request, 'user', None)
        authenticated = bool(viewer and viewer.is_authenticated)
        own = authenticated and viewer.pk == participant.pk
        staff = authenticated and viewer.is_staff
        involved = authenticated and viewer.pk in (booking.owner_id, booking.renter_id)
        visible = own or (involved and booking.status in self.CONTACT_STATUSES)
        email_visible = own
        phone_visible = visible
        # Preserve the legacy detail payload for staff acting as administrators.
        # Staff participating in a booking follow the same rules as other participants.
        if staff and not involved and isinstance(self, BookingDetailSerializer):
            owner_visible = booking.status not in {'pending_approval', 'rejected', 'expired'}
            visible = role == 'owner' and owner_visible
            phone_visible = role == 'renter' or owner_visible
            email_visible = role == 'renter' or owner_visible
        address = participant.addresses.first()
        address_info = {
            'locality': address.area if address else '',
            'city': address.city if address else '',
            'state': address.state if address else '',
            'is_redacted': not visible,
        }
        if visible:
            address_info.update({
                key: getattr(address, key, '') if address else ''
                for key in ('house_number', 'address', 'area', 'landmark', 'pincode', 'country')
            })
            address_info['full_formatted_address'] = (
                f"{address.house_number}, {address.address}, {address.area}, "
                f"{address.landmark + ', ' if address.landmark else ''}"
                f"{address.city}, {address.state} - {address.pincode}"
                if address else "Pickup address will be provided by owner."
            )
        else:
            address_info['notice'] = 'Contact details are available only for approved, active, or completed bookings.'
        data = {
            'id': participant.pk,
            'full_name': participant.full_name or ('Host' if role == 'owner' else 'Renter'),
            'email': participant.email if email_visible else '',
            'phone_number': participant.phone_number if phone_visible else '',
            'address_info': address_info,
        }
        if role == 'owner':
            profile = getattr(participant, 'profile', None)
            photo = profile.profile_image if profile else None
            data.update({
                'is_verified': participant.is_email_verified or participant.is_phone_verified,
                'profile_image': request.build_absolute_uri(photo.url) if photo and request else (photo.url if photo else None),
            })
        return data

    def can_act(self, booking, role):
        request = self.context.get('request')
        viewer = getattr(request, 'user', None)
        return bool(viewer and viewer.is_authenticated and (
            viewer.is_staff or viewer.pk == getattr(booking, role + '_id')))

    def get_owner(self, obj):
        return self.participant_data(obj, obj.owner, 'owner')

    def get_renter(self, obj):
        return self.participant_data(obj, obj.renter, 'renter')


class BookingListSerializer(BookingParticipantPrivacyMixin, serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    item = BookingItemSummarySerializer(read_only=True)
    owner = serializers.SerializerMethodField()
    renter = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    can_pickup = serializers.SerializerMethodField()
    can_return = serializers.SerializerMethodField()
    can_report_problem = serializers.SerializerMethodField()
    picked_up_at = serializers.DateTimeField(read_only=True)
    picked_up_at_display = serializers.CharField(read_only=True)
    return_deadline = serializers.DateTimeField(read_only=True)
    return_deadline_display = serializers.CharField(read_only=True)
    returned_at = serializers.DateTimeField(read_only=True)
    returned_at_display = serializers.CharField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'booking_reference', 'status', 'status_display',
            'payment_status', 'payment_status_display',
            'start_date', 'end_date', 'duration_days', 'requested_quantity',
            'daily_price', 'rental_amount', 'deposit_amount', 'total_amount',
            'item', 'owner', 'renter',
            'can_cancel', 'can_pickup', 'can_return', 'can_report_problem',
            'picked_up_at', 'picked_up_at_display',
            'return_deadline', 'return_deadline_display',
            'returned_at', 'returned_at_display',
            'created_at', 'rejection_reason', 'cancellation_reason'
        ]

    def get_can_cancel(self, obj):
        return self.can_act(obj, 'renter') and obj.can_renter_cancel()

    def get_can_pickup(self, obj):
        return self.can_act(obj, 'owner') and obj.status == 'waiting_for_pickup' and obj.is_payment_verified()

    def get_can_return(self, obj):
        return self.can_act(obj, 'owner') and obj.status == 'rental_in_progress'

    def get_can_report_problem(self, obj):
        return self.can_act(obj, 'renter') and obj.status == 'rental_in_progress'


class BookingDetailSerializer(BookingParticipantPrivacyMixin, serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    item = serializers.SerializerMethodField()
    owner = serializers.SerializerMethodField()
    renter = serializers.SerializerMethodField()
    issue_reports = IssueReportSerializer(many=True, read_only=True)
    can_cancel = serializers.SerializerMethodField()
    can_pickup = serializers.SerializerMethodField()
    can_return = serializers.SerializerMethodField()
    can_report_problem = serializers.SerializerMethodField()
    picked_up_at_display = serializers.CharField(read_only=True)
    return_deadline = serializers.DateTimeField(read_only=True)
    return_deadline_display = serializers.CharField(read_only=True)
    returned_at_display = serializers.CharField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            'id', 'booking_reference', 'status', 'status_display',
            'payment_status', 'payment_status_display',
            'start_date', 'end_date', 'duration_days', 'requested_quantity',
            'daily_price', 'rental_amount', 'deposit_amount', 'total_amount',
            'item', 'owner', 'renter', 'issue_reports',
            'approved_at', 'rejected_at', 'rejection_reason',
            'cancelled_at', 'cancellation_reason',
            'picked_up_at', 'picked_up_at_display',
            'return_deadline', 'return_deadline_display',
            'returned_at', 'returned_at_display',
            'payment_verified_at',
            'can_cancel', 'can_pickup', 'can_return', 'can_report_problem',
            'created_at', 'updated_at'
        ]

    def get_can_cancel(self, obj):
        return self.can_act(obj, 'renter') and obj.can_renter_cancel()

    def get_can_pickup(self, obj):
        return self.can_act(obj, 'owner') and obj.status == 'waiting_for_pickup' and obj.is_payment_verified()

    def get_can_return(self, obj):
        return self.can_act(obj, 'owner') and obj.status == 'rental_in_progress'

    def get_can_report_problem(self, obj):
        return self.can_act(obj, 'renter') and obj.status == 'rental_in_progress'

    def get_item(self, obj):
        item = obj.item
        req = self.context.get('request')
        primary_img = item.primary_image_url
        if primary_img and req and not primary_img.startswith('http'):
            primary_img = req.build_absolute_uri(primary_img)

        images = []
        for img in item.images.all():
            if img.image:
                images.append(req.build_absolute_uri(img.image.url) if req else img.image.url)

        return {
            'id': item.id,
            'name': item.name,
            'slug': item.slug,
            'description': item.description,
            'category_id': item.category_id,
            'category_name': item.category.name,
            'category_icon': item.category.icon,
            'primary_image_url': primary_img,
            'images': images,
            'rental_price': str(item.rental_price),
            'deposit': str(item.deposit),
            'rental_kit': list(item.rental_kit_items.values_list('name', flat=True)),
        }

class BookingCreateSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    requested_quantity = serializers.IntegerField(required=False, default=1, min_value=1)

    def validate_start_date(self, value):
        today = timezone.localdate()
        if value < today:
            raise serializers.ValidationError("Rental start date cannot be in the past.")
        return value

    def validate(self, attrs):
        start_date = attrs['start_date']
        end_date = attrs['end_date']

        if end_date <= start_date:
            raise serializers.ValidationError({"end_date": "End date must be after start date."})

        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication is required to book an item.")

        user = request.user
        item_id = attrs['item_id']
        requested_quantity = attrs['requested_quantity']

        # Mandatory user address validation
        user_address = user.addresses.first()
        if not user_address:
            raise serializers.ValidationError(
                "Please complete your address before booking."
            )
        required_fields = ['full_name', 'house_number', 'address', 'area', 'city', 'state', 'pincode']
        for field in required_fields:
            val = getattr(user_address, field, None)
            if not val or not str(val).strip():
                raise serializers.ValidationError(
                    "Please complete your address before booking."
                )

        # Atomic transaction and row-level locking on Item
        with transaction.atomic():
            try:
                item = Item.objects.select_for_update().get(pk=item_id)
            except Item.DoesNotExist:
                raise serializers.ValidationError({"item_id": "Rental item not found."})

            if item.is_deleted or not item.is_published:
                raise serializers.ValidationError({"item_id": "This item is currently unavailable for rent."})

            if not item.category.is_active or item.category.is_deleted:
                raise serializers.ValidationError({"item_id": "The category for this item is currently inactive."})

            if not item.owner:
                raise serializers.ValidationError({"item_id": "This item cannot be booked because it has no assigned owner."})

            if item.owner_id == user.id:
                raise serializers.ValidationError("You cannot book your own item.")

            # Pending requests do not reserve capacity. Only approved or active
            # rentals reduce date availability under the Option A policy.
            availability = get_item_availability(item, start_date, end_date)
            if requested_quantity > availability['available_stock']:
                raise serializers.ValidationError(
                    {'requested_quantity':
                     f'Requested quantity is unavailable. Only {availability["available_stock"]} items are currently available for these dates.'}
                )

        attrs['item'] = item
        return attrs

    def create(self, validated_data):
        item = validated_data['item']
        start_date = validated_data['start_date']
        end_date = validated_data['end_date']
        renter = self.context['request'].user
        requested_quantity = validated_data['requested_quantity']

        # Rental duration calculated strictly as difference between start date and return date
        # Return date is not counted as an extra rental day
        duration_days = (end_date - start_date).days
        if duration_days <= 0:
            raise serializers.ValidationError({"end_date": "Rental duration must be at least 1 day."})
        daily_price = item.rental_price
        deposit_amount = item.deposit if item.deposit is not None else Decimal('0.00')
        rental_amount = daily_price * duration_days * requested_quantity
        deposit_amount = deposit_amount * requested_quantity
        total_amount = rental_amount + deposit_amount

        # Owner snapshot: strictly derived from item.owner
        if not item.owner:
            raise serializers.ValidationError({"item_id": "This item cannot be booked because it has no owner."})
        owner = item.owner

        with transaction.atomic():
            # Re-lock and double check inside atomic block
            locked_item = Item.objects.select_for_update().get(pk=item.pk)
            availability = get_item_availability(locked_item, start_date, end_date)
            if requested_quantity > availability['available_stock']:
                raise serializers.ValidationError(
                    {'requested_quantity':
                     f'Requested quantity is unavailable. Only {availability["available_stock"]} items are currently available for these dates.'}
                )

            if locked_item.owner_id == renter.pk:
                raise serializers.ValidationError('You cannot book your own item.')
            if not locked_item.owner_id:
                raise serializers.ValidationError({'item_id': 'This item has no assigned owner.'})
            daily_price = locked_item.rental_price
            deposit_amount = locked_item.deposit * requested_quantity
            rental_amount = daily_price * duration_days * requested_quantity
            total_amount = rental_amount + deposit_amount
            owner = locked_item.owner
            booking = Booking.objects.create(
                renter=renter,
                item=locked_item,
                owner=owner,
                start_date=start_date,
                end_date=end_date,
                duration_days=duration_days,
                requested_quantity=requested_quantity,
                daily_price=daily_price,
                rental_amount=rental_amount,
                deposit_amount=deposit_amount,
                total_amount=total_amount,
                status='pending_approval',
                payment_status='pending'
            )
            notify_booking_event(booking, 'requested')

        return booking


class AvailabilityNotificationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilityNotificationRequest
        fields = ['id', 'item', 'start_date', 'end_date', 'is_notified', 'created_at']
        read_only_fields = ['id', 'is_notified', 'created_at']


class InAppNotificationSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)
    booking_status = serializers.CharField(source='booking.status', read_only=True)
    can_respond = serializers.SerializerMethodField()

    def get_can_respond(self, obj):
        request = self.context.get('request')
        return bool(request and obj.booking_id and obj.event == 'requested'
                    and obj.booking.item.owner_id == request.user.pk
                    and obj.booking.status == 'pending_approval'
                    and not obj.booking.is_expired_pending())

    class Meta:
        model = InAppNotification
        fields = ['id', 'title', 'message', 'item', 'item_name', 'is_read', 'created_at', 'booking', 'event', 'booking_status', 'can_respond']
        read_only_fields = ['id', 'created_at']


