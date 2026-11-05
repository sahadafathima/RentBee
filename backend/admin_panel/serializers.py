
from rest_framework import serializers
from users.models import User
from addresses.models import Address


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
