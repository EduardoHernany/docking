# macromolecules/views.py
from rest_framework import viewsets, permissions, filters, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from .models import MacromoleculeType, Macromolecule
from .serializers import (
    MacromoleculeTypeSerializer,
    MacromoleculeSerializer,
    MacromoleculeCreateSerializer,
)


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    GET/HEAD/OPTIONS liberados para autenticados; escrita só para staff.
    Ajuste conforme sua política.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return request.user and request.user.is_authenticated
        return request.user and request.user.is_staff


def _as_bool(val):
    if val is None:
        return None
    s = str(val).strip().lower()
    return s in {"1", "true", "t", "yes", "y", "on"}


@extend_schema(
    tags=["Macromolecule Types"],
    parameters=[
        OpenApiParameter(
            name="search",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Busca por nome do tipo (name)."
        ),
        OpenApiParameter(
            name="active",
            type=OpenApiTypes.BOOL,
            location=OpenApiParameter.QUERY,
            description="Filtra por ativos (true/false)."
        ),
        OpenApiParameter(
            name="ordering",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Ordenação (ex.: name, -created_at)."
        ),
    ],
)
class MacromoleculeTypeViewSet(viewsets.ModelViewSet):
    queryset = MacromoleculeType.objects.all().order_by("name")
    serializer_class = MacromoleculeTypeSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["name", "created_at", "updated_at"]

    def get_queryset(self):
        qs = super().get_queryset()
        active = _as_bool(self.request.query_params.get("active"))
        if active is not None:
            qs = qs.filter(active=active)
        return qs


@extend_schema(tags=["Macromolecules"])
class MacromoleculeViewSet(viewsets.ModelViewSet):
    queryset = Macromolecule.objects.select_related("type").all().order_by("-created_at")
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nome", "rec", "ligante_original"]
    ordering_fields = ["created_at", "updated_at", "nome"]
    parser_classes = [MultiPartParser, FormParser]  # necessário para uploads

    def get_serializer_class(self):
        # para POST, usamos o serializer com FileField
        if self.action == "create":
            return MacromoleculeCreateSerializer
        return MacromoleculeSerializer

    @extend_schema(
        tags=["Macromolecules"],
        # drf-spectacular inferirá multipart/form-data pelos FileField do serializer
        request=MacromoleculeCreateSerializer,
        responses={201: MacromoleculeSerializer},
    )
    def create(self, request, *args, **kwargs):
        """
        Criação com upload:
        - Salva os arquivos em <BASE>/molecules/<type.name>/<redocking>/<recptorFile.filename>/arquivos recebidos
        - Preenche rec = nome do arquivo de receptor
        - Preenche ligante_original = nome do arquivo de ligante
        - Salva pathFilefld = caminho da pasta acima
        """
        create_serializer = MacromoleculeCreateSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        create_serializer.is_valid(raise_exception=True)
        instance = create_serializer.save()

        read_serializer = MacromoleculeSerializer(instance, context=self.get_serializer_context())
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)
