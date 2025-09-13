# processes/serializers.py
from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Process
from macromolecules.models import MacromoleculeType

User = get_user_model()


class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name"]


class MacromoleculeTypeMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = MacromoleculeType
        fields = ["id", "name"]


class ProcessSerializer(serializers.ModelSerializer):
    # escrita por ID
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    type = serializers.PrimaryKeyRelatedField(queryset=MacromoleculeType.objects.all())

    # leitura detalhada
    user_detail = UserMiniSerializer(source="user", read_only=True)
    type_detail = MacromoleculeTypeMiniSerializer(source="type", read_only=True)

    class Meta:
        model = Process
        fields = [
            "id",
            "nome",
            "type",
            "type_detail",
            "redocking",
            "status",
            "resultado_final",
            "pathFileSDF",
            "user",
            "user_detail",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
