
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Profile

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False
    )





class ProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.full_name")
    email = serializers.EmailField(
        source="user.email",
        read_only=True
    )
    phone_number = serializers.CharField(
        source="user.phone_number"
    )

    class Meta:
        model = Profile
        fields = [
            "full_name",
            "email",
            "phone_number",
            "profile_image",
        ]

    def validate_phone_number(self, value):
        user = self.instance.user

        if User.objects.filter(
            phone_number=value
        ).exclude(pk=user.pk).exists():
            raise serializers.ValidationError(
                "This phone number is already registered."
            )

        return value

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        user = instance.user

        for field, value in user_data.items():
            setattr(user, field, value)

        user.save()

        return super().update(instance, validated_data)
