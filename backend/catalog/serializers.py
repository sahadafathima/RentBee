from rest_framework import serializers
from .models import Category, Item, ItemImage, WishlistItem


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
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_deleted=False, is_active=True),
        source='category'
    )
    category_name = serializers.CharField(source='category.name', read_only=True)
    category_icon = serializers.CharField(source='category.icon', read_only=True)
    owner_name = serializers.SerializerMethodField()
    owner_details = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    rental_kit = serializers.SerializerMethodField()
    deposit = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    images = ItemImageSerializer(many=True, read_only=True)
    primary_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = [
            'id', 'name', 'slug', 'description', 'category_id', 'category_name',
            'category_icon', 'owner', 'owner_name', 'owner_details', 'rental_price',
            'stock', 'deposit', 'rental_kit', 'is_available', 'is_published', 'is_deleted',
            'images', 'primary_image_url', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'owner', 'created_at', 'updated_at', 'is_deleted']

    def get_rental_kit(self, obj):
        return list(obj.rental_kit_items.values_list('name', flat=True))

    def get_is_available(self, obj):
        return bool(obj.stock and obj.stock > 0)

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
            'name': getattr(obj.owner, 'full_name', None) or obj.owner.email.split('@')[0],
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
            return getattr(obj.owner, 'full_name', None) or obj.owner.email
        return 'Admin'

    def to_internal_value(self, data):
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

