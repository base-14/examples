from typing import Any

from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ["id", "email", "name", "bio", "image", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class RegisterSerializer(serializers.ModelSerializer[User]):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ["email", "name", "password"]

    def create(self, validated_data: dict[str, Any]) -> User:
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):  # type: ignore[type-arg]
    email = serializers.EmailField()
    password = serializers.CharField()


class TokenSerializer(serializers.Serializer):  # type: ignore[type-arg]
    access_token = serializers.CharField()
    token_type = serializers.CharField(default="Bearer")
