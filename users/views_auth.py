# users/views_auth.py
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import (
    AuthLoginSerializer,
    AuthTokenResponseSerializer,
    UserSerializer,
)

User = get_user_model()


def _bool_attr(obj, name, default=True):
    # util: lida com campos custom como 'active' coexistindo com 'is_active'
    return getattr(obj, name, default)


@extend_schema(
    tags=["Auth"],
    request=AuthLoginSerializer,
    responses={200: AuthTokenResponseSerializer, 401: None},
)
class AuthLoginPasswordView(APIView):
    """
    POST /api/auth/login/password
    body: { "email": "...", "password": "..." }
    resp: { "access_token": "...", "token_type": "Bearer" }
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = AuthLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip()
        password = serializer.validated_data["password"]

        # autenticação por e-mail (case-insensitive)
        user = User.objects.filter(email__iexact=email).first()
        if not user or not check_password(password, user.password):
            return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

        # bloqueios básicos
        if not user.is_active or not _bool_attr(user, "active", True) or _bool_attr(user, "deleted", False):
            return Response({"detail": "User is inactive or deleted"}, status=status.HTTP_401_UNAUTHORIZED)

        # Gera somente access_token (sem refresh, conforme seu contrato)
        access = RefreshToken.for_user(user).access_token
        return Response(
            {"access_token": str(access), "token_type": "Bearer"},
            status=status.HTTP_200_OK,
        )


@extend_schema(
    tags=["Auth"],
    responses={200: UserSerializer},
)
class AuthLoginProfileView(APIView):
    """
    GET /api/auth/login/profile
    resp: { "user": <User> }
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        data = UserSerializer(request.user).data
        return Response({"user": data}, status=status.HTTP_200_OK)
