from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from catalog.models import Item
from catalog.serializers import ItemImageSerializer
from .models import Booking, IssueReport, AvailabilityNotificationRequest, InAppNotification
from .services import check_item_conflicts


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
        return getattr(obj.renter, 'full_name', '') or obj.renter.email

    def get_owner_name(self, obj):
        return getattr(obj.owner, 'full_name', '') or obj.owner.email

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


class BookingListSerializer(serializers.ModelSerializer):
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
            'start_date', 'end_date', 'duration_days',
            'daily_price', 'rental_amount', 'deposit_amount', 'total_amount',
            'item', 'owner', 'renter',
            'can_cancel', 'can_pickup', 'can_return', 'can_report_problem',
            'picked_up_at', 'picked_up_at_display',
            'return_deadline', 'return_deadline_display',
            'returned_at', 'returned_at_display',
            'created_at', 'rejection_reason', 'cancellation_reason'
        ]

    def get_owner(self, obj):
        owner = obj.owner
        profile_img = None
        if hasattr(owner, 'profile') and owner.profile and owner.profile.profile_image:
            req = self.context.get('request')
            profile_img = req.build_absolute_uri(owner.profile.profile_image.url) if req else owner.profile.profile_image.url

        return {
            'id': owner.id,
            'full_name': getattr(owner, 'full_name', '') or owner.email.split('@')[0],
            'email': owner.email,
            'is_verified': getattr(owner, 'is_email_verified', False) or getattr(owner, 'is_phone_verified', False),
            'profile_image': profile_img,
        }

    def get_renter(self, obj):
        renter = obj.renter
        return {
            'id': renter.id,
            'full_name': getattr(renter, 'full_name', '') or renter.email.split('@')[0],
            'email': renter.email,
            'phone_number': getattr(renter, 'phone_number', ''),
        }

    def get_can_cancel(self, obj):
        return obj.can_renter_cancel()

    def get_can_pickup(self, obj):
        return obj.status == 'waiting_for_pickup' and obj.is_payment_verified()

    def get_can_return(self, obj):
        return obj.status == 'rental_in_progress'

    def get_can_report_problem(self, obj):
        return obj.status == 'rental_in_progress'


class BookingDetailSerializer(serializers.ModelSerializer):
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
            'start_date', 'end_date', 'duration_days',
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
        return obj.can_renter_cancel()

    def get_can_pickup(self, obj):
        return obj.status == 'waiting_for_pickup' and obj.is_payment_verified()

    def get_can_return(self, obj):
        return obj.status == 'rental_in_progress'

    def get_can_report_problem(self, obj):
        return obj.status == 'rental_in_progress'

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

    def get_owner(self, obj):
        owner = obj.owner
        req = self.context.get('request')
        profile_img = None
        if hasattr(owner, 'profile') and owner.profile and owner.profile.profile_image:
            profile_img = req.build_absolute_uri(owner.profile.profile_image.url) if req else owner.profile.profile_image.url

        addr = owner.addresses.first()

        # Strict Privacy Gate:
        # Full address & direct contact number are ONLY revealed once the booking reaches waiting_for_pickup,
        # rental_in_progress, or completed.
        # During pending_approval, full address and phone number are REDACTED.
        is_pre_pickup_pending = obj.status in ['pending_approval', 'rejected', 'expired']

        if is_pre_pickup_pending:
            return {
                'id': owner.id,
                'full_name': getattr(owner, 'full_name', '') or owner.email.split('@')[0],
                'email': '',  # redacted
                'phone_number': '',  # redacted
                'is_verified': getattr(owner, 'is_email_verified', False) or getattr(owner, 'is_phone_verified', False),
                'profile_image': profile_img,
                'address_info': {
                    'locality': addr.area if addr else '',
                    'city': addr.city if addr else '',
                    'state': addr.state if addr else '',
                    'is_redacted': True,
                    'notice': 'Exact pickup address and phone number will be revealed once the owner approves your booking.'
                }
            }

        # Confirmed stages: reveal full pickup address and contact details to authorized participant
        return {
            'id': owner.id,
            'full_name': getattr(owner, 'full_name', '') or owner.email.split('@')[0],
            'email': owner.email,
            'phone_number': getattr(owner, 'phone_number', ''),
            'is_verified': getattr(owner, 'is_email_verified', False) or getattr(owner, 'is_phone_verified', False),
            'profile_image': profile_img,
            'address_info': {
                'house_number': addr.house_number if addr else '',
                'address': addr.address if addr else '',
                'area': addr.area if addr else '',
                'landmark': addr.landmark if addr else '',
                'city': addr.city if addr else '',
                'state': addr.state if addr else '',
                'pincode': addr.pincode if addr else '',
                'country': addr.country if addr else 'India',
                'full_formatted_address': (
                    f"{addr.house_number}, {addr.address}, {addr.area}, {addr.landmark + ', ' if addr and addr.landmark else ''}{addr.city}, {addr.state} - {addr.pincode}"
                    if addr else "Pickup address will be provided by owner."
                ),
                'is_redacted': False,
            }
        }

    def get_renter(self, obj):
        renter = obj.renter
        return {
            'id': renter.id,
            'full_name': getattr(renter, 'full_name', '') or renter.email.split('@')[0],
            'email': renter.email,
            'phone_number': getattr(renter, 'phone_number', ''),
        }


class BookingCreateSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()

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

            if item.owner and item.owner_id == user.id:
                raise serializers.ValidationError("You cannot book your own item.")

            # Date overlap & concurrency check
            conflicting = check_item_conflicts(item.id, start_date, end_date)
            if conflicting.exists():
                raise serializers.ValidationError(
                    "This item is already booked or reserved for the selected dates. Please choose different dates."
                )

        attrs['item'] = item
        return attrs

    def create(self, validated_data):
        item = validated_data['item']
        start_date = validated_data['start_date']
        end_date = validated_data['end_date']
        renter = self.context['request'].user

        # Rental duration calculated strictly as difference between start date and return date
        # Return date is not counted as an extra rental day
        duration_days = (end_date - start_date).days
        if duration_days <= 0:
            raise serializers.ValidationError({"end_date": "Rental duration must be at least 1 day."})
        daily_price = item.rental_price
        deposit_amount = item.deposit if item.deposit is not None else Decimal('0.00')
        rental_amount = daily_price * duration_days
        total_amount = rental_amount + deposit_amount

        # Owner snapshot: derived from item.owner at creation
        owner = item.owner or renter

        with transaction.atomic():
            # Re-lock and double check inside atomic block
            locked_item = Item.objects.select_for_update().get(pk=item.pk)
            conflicting = check_item_conflicts(locked_item.id, start_date, end_date)
            if conflicting.exists():
                raise serializers.ValidationError(
                    "This item is already booked or reserved for the selected dates. Please choose different dates."
                )

            booking = Booking.objects.create(
                renter=renter,
                item=locked_item,
                owner=owner,
                start_date=start_date,
                end_date=end_date,
                duration_days=duration_days,
                daily_price=daily_price,
                rental_amount=rental_amount,
                deposit_amount=deposit_amount,
                total_amount=total_amount,
                status='pending_approval',
                payment_status='pending'
            )

        return booking


class AvailabilityNotificationRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AvailabilityNotificationRequest
        fields = ['id', 'item', 'start_date', 'end_date', 'is_notified', 'created_at']
        read_only_fields = ['id', 'is_notified', 'created_at']


class InAppNotificationSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='item.name', read_only=True)

    class Meta:
        model = InAppNotification
        fields = ['id', 'title', 'message', 'item', 'item_name', 'is_read', 'created_at']
        read_only_fields = ['id', 'created_at']


