import json
from django.utils import timezone
from django.db.models import Q, Count
from rest_framework import serializers
from .models import Category, Item, ItemImage, WishlistItem, RentalKitItem


class CategorySerializer(serializers.ModelSerializer):
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'description', 'icon', 'items_count',
            'is_active', 'is_deleted', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'items_count', 'created_at', 'updated_at', 'is_deleted']

    def get_items_count(self, obj):
        if hasattr(obj, 'items_count'):
            return obj.items_count
        return obj.items.filter(is_deleted=False).count()

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError('Name is required.')
        # Prevent creating a real category named "All Categories" — it's a UI-only sentinel
        if name.lower() == 'all categories':
            raise serializers.ValidationError('"All Categories" is a reserved filter label and cannot be used as a category name.')
        qs = Category.objects.filter(name__iexact=name, is_deleted=False)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('A category with this name already exists.')
        return name

    def validate_icon(self, value):
        # Prevent using the '▦' icon for real categories — it is reserved for the "All Categories" UI sentinel
        if value == '▦':
            raise serializers.ValidationError(
                'The ▦ icon is reserved for the "All Categories" filter. Please choose a different icon.'
            )
        return value

    def validate(self, attrs):
        icon = attrs.get('icon', getattr(self.instance, 'icon', None))
        is_active = attrs.get('is_active', getattr(self.instance, 'is_active', True))
        is_deleted = attrs.get('is_deleted', getattr(self.instance, 'is_deleted', False))

        if icon and is_active and not is_deleted:
            qs = Category.objects.filter(icon=icon, is_active=True, is_deleted=False)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                assigned_name = qs.first().name
                raise serializers.ValidationError({
                    'icon': f'This icon is already assigned to active category "{assigned_name}".'
                })
        return attrs


class ItemImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemImage
        fields = ['id', 'image', 'is_primary', 'created_at']


class ItemSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if isinstance(self.instance, Item):
            # Retain a category retired after publication, but do not switch to one.
            self.fields['category_id'].queryset = Category.objects.filter(
                Q(is_deleted=False, is_active=True) | Q(pk=self.instance.category_id))

    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_deleted=False, is_active=True),
        source='category'
    )
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_icon = serializers.CharField(source='category.icon', read_only=True)
    owner_name = serializers.SerializerMethodField()
    booking_activity = serializers.SerializerMethodField()
    owner_details = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    total_stock = serializers.IntegerField(source='stock', read_only=True)
    available_stock = serializers.SerializerMethodField()
    availability_reason = serializers.SerializerMethodField()
    is_currently_booked = serializers.SerializerMethodField()
    current_booking = serializers.SerializerMethodField()
    is_booked_by_current_user = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()
    user_booking = serializers.SerializerMethodField()
    rental_kit = serializers.SerializerMethodField()
    deposit = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    is_published = serializers.BooleanField(default=True, required=False)
    images = ItemImageSerializer(many=True, read_only=True)
    primary_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            'id', 'name', 'slug', 'description', 'category_id', 'category_name',
            'category_icon', 'owner', 'owner_name', 'is_owner', 'booking_activity', 'owner_details', 'rental_price',
            'stock', 'total_stock', 'available_stock', 'availability_reason', 'deposit', 'rental_kit', 'is_available', 'is_currently_booked',
            'current_booking', 'is_booked_by_current_user', 'user_booking',
            'is_published', 'is_deleted',
            'images', 'primary_image_url', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'owner', 'created_at', 'updated_at', 'is_deleted']

    CONFIRMED_ACTIVE_STATUSES = ['waiting_for_pickup', 'rental_in_progress']

    def _get_relevant_active_booking(self, queryset, today):
        """
        Selects the most relevant active confirmed booking from the queryset:
        1. Prioritize a rental actively in progress today (start_date <= today <= end_date).
        2. Otherwise, the earliest upcoming active confirmed rental (end_date >= today, ordered by start_date).
        """
        in_progress = queryset.filter(
            status='rental_in_progress',
            start_date__lte=today,
            end_date__gte=today
        ).order_by('end_date').first()

        if in_progress:
            return in_progress

        return queryset.filter(
            status__in=self.CONFIRMED_ACTIVE_STATUSES,
            end_date__gte=today
        ).order_by('start_date').first()

    def get_rental_kit(self, obj):
        return list(obj.rental_kit_items.values_list('name', flat=True))

    def get_user_booking(self, obj):
        if hasattr(obj, '_cached_user_booking'):
            return obj._cached_user_booking

        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            obj._cached_user_booking = None
            return None

        today = timezone.localdate()
        user_qs = obj.bookings.filter(
            renter_id=request.user.id,
            status__in=self.CONFIRMED_ACTIVE_STATUSES,
            end_date__gte=today
        )
        active_user_booking = self._get_relevant_active_booking(user_qs, today)

        if not active_user_booking:
            obj._cached_user_booking = None
            return None

        data = {
            'id': active_user_booking.id,
            'booking_reference': active_user_booking.booking_reference,
            'start_date': str(active_user_booking.start_date),
            'end_date': str(active_user_booking.end_date),
            'status': active_user_booking.status,
        }
        obj._cached_user_booking = data
        return data

    def get_is_booked_by_current_user(self, obj):
        return bool(self.get_user_booking(obj))

    def get_current_booking(self, obj):
        if hasattr(obj, '_cached_current_booking'):
            return obj._cached_current_booking

        request = self.context.get('request')
        today = timezone.localdate()

        other_qs = obj.bookings.filter(
            status__in=self.CONFIRMED_ACTIVE_STATUSES,
            end_date__gte=today
        )
        if request and request.user and request.user.is_authenticated:
            other_qs = other_qs.exclude(renter_id=request.user.id)

        other_booking = self._get_relevant_active_booking(other_qs, today)

        if not other_booking:
            obj._cached_current_booking = None
            return None

        data = {
            'start_date': str(other_booking.start_date),
            'end_date': str(other_booking.end_date),
            'next_available_date': self._next_available_date(obj),
            'status': other_booking.status,
        }
        obj._cached_current_booking = data
        return data

    def _next_available_date(self, obj):
        from bookings.services import get_next_available_date
        return get_next_available_date(obj)

    def _availability(self, obj):
        from bookings.services import get_item_availability
        if not hasattr(obj, '_stock_availability'):
            obj._stock_availability = get_item_availability(obj)
        return obj._stock_availability

    def get_available_stock(self, obj):
        return self._availability(obj)['available_stock']

    def get_availability_reason(self, obj):
        return self._availability(obj)['availability_reason']

    def get_is_currently_booked(self, obj):
        data = self._availability(obj)
        return data['available_stock'] == 0 and data['availability_reason'] == 'reserved'

    def get_is_available(self, obj):
        return self._availability(obj)['is_available']

    def get_is_owner(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return request.user.pk == obj.owner_id

    def get_booking_activity(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated or request.user.pk != obj.owner_id:
            return None
        return dict(obj.bookings.values('status').annotate(count=Count('pk')).values_list('status', 'count'))

    def get_owner_details(self, obj):
        if not obj.owner:
            return {
                'name': 'RentBee Lender',
                'locality': '',
                'nearest_location': '',
                'city': '',
                'state': '',
            }
        addr = obj.owner.addresses.first()
        return {
            'name': getattr(obj.owner, 'full_name', None) or 'RentBee Lender',
            'locality': addr.area if addr else '',
            'nearest_location': addr.landmark if addr else '',
            'city': addr.city if addr else '',
            'state': addr.state if addr else '',
        }

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

    def get_owner_name(self, obj):
        if obj.owner:
            return getattr(obj.owner, 'full_name', None) or 'RentBee Lender'
        return 'Admin'

    def to_internal_value(self, data):
        # rental_kit is read-only in the response serializer; views consume the
        # raw input separately. Validate it here, before any view saves/deletes.
        if 'rental_kit' in data:
            entries = data.get('rental_kit')
            if isinstance(entries, str):
                try:
                    entries = json.loads(entries)
                except json.JSONDecodeError:
                    entries = [entry.strip() for entry in entries.split(',') if entry.strip()]
            if not isinstance(entries, list):
                raise serializers.ValidationError({'rental_kit': 'Expected a list of rental-kit entries.'})
            limit = RentalKitItem._meta.get_field('name').max_length
            errors = {}
            for index, entry in enumerate(entries):
                name = entry.get('name', '') if isinstance(entry, dict) else entry
                if not isinstance(name, str):
                    errors[str(index)] = [f'Entry {index + 1} must be text.']
                elif len(name.strip()) > limit:
                    errors[str(index)] = [
                        f'Entry {index + 1} must be at most {limit} characters '
                        f'(received {len(name.strip())}).']
            if errors:
                raise serializers.ValidationError({'rental_kit': errors})
        # Handle mutable copy if QueryDict from multipart form data
        if hasattr(data, '_mutable'):
            data._mutable = True
        elif hasattr(data, 'copy'):
            data = data.copy()
        if 'deposit' in data:
            val = data.get('deposit')
            if val is None or val == '' or (isinstance(val, str) and val.strip() == ''):
                data['deposit'] = '0.00'
        return super().to_internal_value(data)

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError('Item name is required.')
        return name

    def validate_rental_price(self, value):
        if value <= 0:
            raise serializers.ValidationError('Rental price must be greater than zero.')
        return value

    def validate_stock(self, value):
        if value < 0:
            raise serializers.ValidationError('Stock quantity cannot be negative.')
        return value

    def validate_deposit(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Deposit amount cannot be negative.')
        return value


class WishlistItemSerializer(serializers.ModelSerializer):
    item = ItemSerializer(read_only=True)

    class Meta:
        model = WishlistItem
        fields = ['id', 'item', 'created_at']
        read_only_fields = ['id', 'created_at']

