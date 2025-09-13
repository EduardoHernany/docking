# users/serializers_password.py
from rest_framework import serializers

class PasswordRecoverySerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    newPassword = serializers.CharField(write_only=True, trim_whitespace=False)
    token = serializers.CharField()
