from django.contrib.auth import get_user_model
from rest_framework import viewsets, permissions, filters
from rest_framework.permissions import AllowAny
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiParameter

from .serializers import UserSerializer

User = get_user_model()


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    GET liberado p/ autenticados; POST/PUT/PATCH/DELETE só admin.
    *Obs.: a ação 'create' é tratada no get_permissions do ViewSet (pública).*
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        # Demais métodos (exceto 'create', ver get_permissions) exigem admin:
        return bool(request.user and request.user.is_staff)


@extend_schema(
    tags=["Users"],
    parameters=[
        OpenApiParameter("search", OpenApiTypes.STR, OpenApiParameter.QUERY,
                         description="Busca por username, email, first_name, last_name"),
        OpenApiParameter("ordering", OpenApiTypes.STR, OpenApiParameter.QUERY,
                         description="Ordenação, ex: username ou -date_joined"),
    ],
)
class UserViewSet(viewsets.ModelViewSet):
    """
    CRUD de usuários.
    - Create: público (sem autenticação)
    - List/Retrieve: autenticado
    - Update/Delete: admin
    """
    queryset = User.objects.all().order_by("-date_joined")
    serializer_class = UserSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering_fields = ["username", "date_joined", "last_login"]

    def get_permissions(self):
        # Torna a ação de criação pública
        if self.action == "create":
            return [AllowAny()]
        return [IsAdminOrReadOnly()]
