# users/views_password.py
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.contrib.auth.tokens import default_token_generator

from rest_framework.views import APIView
from rest_framework import permissions, status
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
from resend.exceptions import ResendError 

from .serializers_password import PasswordRecoverySerializer, PasswordUpdateSerializer
from .emails import send_password_recovery_email

User = get_user_model()


@extend_schema(
    tags=["Auth"],
    request=PasswordRecoverySerializer,
    responses={200: {"type": "object", "properties": {"message": {"type": "string"}}},
               404: {"type": "object", "properties": {"detail": {"type": "string"}}}},
)
class PasswordRecoveryView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = PasswordRecoverySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        email = ser.validated_data["email"].strip().lower()

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            # Se quiser não revelar existência, retorne 200 sempre:
            # return Response({"message": "Email with recovery code sent successfully"}, status=200)
            return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        token = default_token_generator.make_token(user)

        try:
            send_password_recovery_email(email, token)
        except ResendError as e:
            # erro do Resend (credenciais, domínio não verificado etc.)
            return Response({"detail": "Email service error"}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as e:
            # outros erros (rede, DNS, etc.)
            return Response({"detail": "Internal email error"}, status=status.HTTP_502_BAD_GATEWAY)

        return Response({"message": "Email with recovery code sent successfully"}, status=status.HTTP_200_OK)


@extend_schema(
    tags=["Auth"],
    request=PasswordUpdateSerializer,
    responses={200: {"type": "object", "properties": {"message": {"type": "string"}}},
               400: {"type": "object", "properties": {"detail": {"type": "string"}}},
               404: {"type": "object", "properties": {"detail": {"type": "string"}}}},
)
class PasswordUpdateView(APIView):
    """
    POST /api/auth/password/update
    body: { "email": "...", "newPassword": "...", "token": "..." }
    resp: { "message": "Password updated successfully" }
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = PasswordUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        email = ser.validated_data["email"].strip().lower()
        new_password = ser.validated_data["newPassword"]
        token = ser.validated_data["token"]

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        # valida token (estateless; depende do hash da senha/last_login etc.)
        if not default_token_generator.check_token(user, token):
            return Response({"detail": "Invalid or expired token"}, status=status.HTTP_400_BAD_REQUEST)

        # valida força da senha (usa validadores do Django)
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as e:
            return Response({"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)

        # troca a senha (isso automaticamente invalida o token do gerador)
        user.set_password(new_password)
        user.save(update_fields=["password"])

        return Response({"message": "Password updated successfully"}, status=status.HTTP_200_OK)
