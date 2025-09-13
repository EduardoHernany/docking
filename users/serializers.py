# users/serializers.py
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from users.models import RoleEnum  # importa para default e choices

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    # unicidade no nível de API
    username = serializers.CharField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all())],
    )
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all())],
    )

    # password write-only e opcional no update
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    # defaults explícitos na API (além dos defaults do model)
    role = serializers.ChoiceField(choices=RoleEnum.choices, default=RoleEnum.USER, required=False)
    deleted = serializers.BooleanField(default=False, required=False)
    is_active = serializers.BooleanField(default=True, required=False)

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "role", "deleted",
            "is_active", "is_staff", "is_superuser",
            "last_login", "date_joined",
            "password",
        ]
        read_only_fields = ["id", "is_staff", "is_superuser", "last_login", "date_joined"]

    def validate_email(self, value: str) -> str:
        # normaliza para minúsculas para consistência com a constraint no banco
        return value.strip().lower()

    def create(self, validated_data):
        # garante defaults caso o caller não envie
        validated_data.setdefault("role", RoleEnum.USER)
        validated_data.setdefault("deleted", False)
        validated_data.setdefault("is_active", True)

        password = validated_data.pop("password", None)
        # normaliza username opcionalmente (caso queira)
        if "username" in validated_data and isinstance(validated_data["username"], str):
            validated_data["username"] = validated_data["username"].strip()

        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        # nunca permita email em branco
        if "email" in validated_data:
            validated_data["email"] = validated_data["email"].strip().lower()

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.set_password(password)
        instance.save()
        return instance

class AuthLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class AuthTokenResponseSerializer(serializers.Serializer):
    access_token = serializers.CharField()
    token_type = serializers.CharField()
