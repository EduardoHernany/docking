# processes/views.py
from rest_framework import viewsets, permissions, filters
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import Process
from .serializers import ProcessSerializer


def _as_bool(val):
    if val is None:
        return None
    s = str(val).strip().lower()
    return s in {"1", "true", "t", "yes", "y", "on"}


class IsOwnerOrAdminOrReadOnly(permissions.BasePermission):
    """
    Leitura: usuário autenticado.
    Escrita: admin OU dono do recurso (process.user == request.user).
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj: Process):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user.is_staff or obj.user_id == request.user.id)


@extend_schema(
    tags=["Processes"],
    parameters=[
        OpenApiParameter("search", OpenApiTypes.STR, OpenApiParameter.QUERY,
                         description="Busca por nome (nome), pathFileSDF, user.username, type.name."),
        OpenApiParameter("type_id", OpenApiTypes.STR, OpenApiParameter.QUERY,
                         description="Filtra pelo UUID do MacromoleculeType."),
        OpenApiParameter("user_id", OpenApiTypes.INT, OpenApiParameter.QUERY,
                         description="Filtra pelo ID do usuário dono."),
        OpenApiParameter("status", OpenApiTypes.STR, OpenApiParameter.QUERY,
                         description="Filtra por status (EM_FILA, PROCESSANDO, CONCLUIDO, ERROR)."),
        OpenApiParameter("redocking", OpenApiTypes.BOOL, OpenApiParameter.QUERY,
                         description="Filtra por redocking (true/false)."),
        OpenApiParameter("ordering", OpenApiTypes.STR, OpenApiParameter.QUERY,
                         description="Ordenação. Ex.: -created_at, status, nome."),
    ],
)
class ProcessViewSet(viewsets.ModelViewSet):
    queryset = Process.objects.select_related("type", "user").all().order_by("-created_at")
    serializer_class = ProcessSerializer
    permission_classes = [IsOwnerOrAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nome", "pathFileSDF", "user__username", "type__name"]
    ordering_fields = ["created_at", "updated_at", "nome", "status"]

    def get_queryset(self):
        qs = super().get_queryset()

        # filtros simples por query params
        type_id = self.request.query_params.get("type_id")
        if type_id:
            qs = qs.filter(type_id=type_id)

        user_id = self.request.query_params.get("user_id")
        if user_id:
            qs = qs.filter(user_id=user_id)

        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)

        redocking = _as_bool(self.request.query_params.get("redocking"))
        if redocking is not None:
            qs = qs.filter(redocking=redocking)

        return qs

    def perform_create(self, serializer):
        """
        Se o caller não mandar 'user', definimos o usuário atual.
        Admin pode criar para terceiros explicitando user.
        """
        user = serializer.validated_data.get("user") or self.request.user
        serializer.save(user=user)
