
from rest_framework import serializers
from users.models import User
from addresses.models import Address
from catalog.models import Item
from bookings.services import get_item_availability


class AdminAddressSerializer(serializers.ModelSerializer):

    class Meta:
        model = Address
        fields = [
            "id",
            "full_name",
            "address",
            "house_number",
            "area",
            "landmark",
            "country",
            "state",
            "city",
            "pincode",
            "address_type",
        ]


class AdminUserSerializer(serializers.ModelSerializer):

    addresses = AdminAddressSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "email",
            "phone_number",
            "addresses",
            "is_email_verified",
            "is_phone_verified",
            "is_active",
            "created_at",
        ]


class AdminInventoryItemSerializer(serializers.ModelSerializer):
    category_id = serializers.IntegerField(source='category.id', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_icon = serializers.CharField(source='category.icon', read_only=True)
    owner = serializers.SerializerMethodField()
    owner_name = serializers.SerializerMethodField()
    owner_email = serializers.SerializerMethodField()
    price_per_day = serializers.DecimalField(source='rental_price', max_digits=10, decimal_places=2, read_only=True)
    security_deposit = serializers.DecimalField(source='deposit', max_digits=10, decimal_places=2, read_only=True)
    primary_image_url = serializers.SerializerMethodField()
    primary_image = serializers.SerializerMethodField()
    total_stock = serializers.IntegerField(source='stock', read_only=True)
    available_stock = serializers.SerializerMethodField()
    reserved_stock = serializers.SerializerMethodField()
    availability_reason = serializers.SerializerMethodField()
    active_bookings_count = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            'id', 'name', 'slug', 'description', 'category_id', 'category_name', 'category_icon',
            'owner', 'owner_name', 'owner_email', 'rental_price', 'deposit',
            'price_per_day', 'security_deposit',
            'stock', 'total_stock', 'reserved_stock', 'available_stock', 'availability_reason',
            'active_bookings_count', 'is_published', 'is_deleted',
            'primary_image_url', 'primary_image', 'created_at', 'updated_at'
        ]

    def _availability(self, obj):
        if not hasattr(obj, '_cached_avail'):
            obj._cached_avail = get_item_availability(obj)
        return obj._cached_avail

    def _resolve_owner_name(self, owner):
        if not owner:
            return None
        # 1. First and last name when available
        first = (getattr(owner, 'first_name', '') or '').strip()
        last = (getattr(owner, 'last_name', '') or '').strip()
        first_last = f"{first} {last}".strip()
        if first_last:
            return first_last
        # 2. full_name attribute
        full = (getattr(owner, 'full_name', '') or '').strip()
        if full:
            return full
        # 3. username fallback
        username = (getattr(owner, 'username', '') or '').strip()
        if username:
            return username
        # 4. email username portion
        email = (getattr(owner, 'email', '') or '').strip()
        if email:
            return email.split('@')[0]
        return None

    def get_owner(self, obj):
        owner = obj.owner
        if not owner:
            return None
        name = self._resolve_owner_name(owner)
        return {
            'id': owner.id,
            'full_name': name,
            'email': getattr(owner, 'email', '') or '',
            'phone': getattr(owner, 'phone_number', '') or '',
        }

    def get_owner_name(self, obj):
        return self._resolve_owner_name(obj.owner)

    def get_owner_email(self, obj):
        return getattr(obj.owner, 'email', None) if obj.owner else None

    def get_primary_image_url(self, obj):
        primary = obj.images.filter(is_primary=True).first() or obj.images.first()
        if primary and primary.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(primary.image.url)
            return primary.image.url
        return None

    def get_primary_image(self, obj):
        return self.get_primary_image_url(obj)

    def get_available_stock(self, obj):
        return self._availability(obj)['available_stock']

    def get_reserved_stock(self, obj):
        avail = self._availability(obj)
        return max(0, obj.stock - avail['available_stock'])

    def get_availability_reason(self, obj):
        return self._availability(obj)['availability_reason']

    def get_active_bookings_count(self, obj):
        return obj.bookings.filter(status__in=['waiting_for_pickup', 'rental_in_progress']).count()

