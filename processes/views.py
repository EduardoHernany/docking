# processes/views.py
import logging
import shutil
from pathlib import Path

from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework import viewsets, permissions, filters, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import action
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from processes.tasks import run_plasmodocking_process
from .models import Process
from .serializers import ProcessSerializer, ProcessCreateSerializer

logger = logging.getLogger(__name__)


class IsOwnerOrAdminOrReadOnly(permissions.BasePermission):
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
        OpenApiParameter("ordering", OpenApiTypes.STR, OpenApiParameter.QUERY,
                         description="Ordenação. Ex.: -created_at, status, nome."),
    ],
)
class ProcessViewSet(viewsets.ModelViewSet):
    queryset = Process.objects.select_related("type", "user").all().order_by("-created_at")
    permission_classes = [IsOwnerOrAdminOrReadOnly]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["nome", "pathFileSDF", "user__username", "type__name"]
    ordering_fields = ["created_at", "updated_at", "nome", "status"]
    parser_classes = [MultiPartParser, FormParser]  # necessário para receber arquivo

    def get_serializer_class(self):
        if self.action == "create":
            return ProcessCreateSerializer
        return ProcessSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        type_id = self.request.query_params.get("type_id")
        if type_id:
            qs = qs.filter(type_id=type_id)
        user_id = self.request.query_params.get("user_id")
        if user_id:
            qs = qs.filter(user_id=user_id)
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    @extend_schema(
        request=ProcessCreateSerializer,
        responses={201: ProcessSerializer},
        tags=["Processes"],
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        user = serializer.validated_data.get("user") or self.request.user
        instance = serializer.save(user=user)
        try:
            run_plasmodocking_process.delay(str(instance.id))
        except Exception:
            instance.status = "ERROR"
            instance.save(update_fields=["status"])
            raise

    # ===== DOWNLOAD DO ZIP =====
    @action(detail=True, methods=["get"], url_path="download-zip")
    def download_zip(self, request, pk=None):
        """
        Baixa o arquivo .zip gerado para este processo.
        """
        process = self.get_object()  # respeita as permissões de objeto
        if not process.pathFileZIP:
            raise Http404("Arquivo compactado ainda não está disponível.")

        file_path = Path(process.pathFileZIP)
        if not file_path.exists() or not file_path.is_file():
            raise Http404("Arquivo compactado não encontrado no servidor.")

        return FileResponse(
            open(file_path, "rb"),
            as_attachment=True,
            filename=file_path.name,
            content_type="application/zip",
        )

    # ===== DELETE + REMOÇÃO DO DIRETÓRIO =====
    def destroy(self, request, *args, **kwargs):
        """
        Ao deletar o Process, remove também o diretório do processo
        (a pasta onde o SDF foi salvo e onde ficam os artefatos).
        """
        instance: Process = self.get_object()

        # Deriva o diretório do processo a partir do pathFileSDF
        proc_dir: Path | None = None
        if instance.pathFileSDF:
            try:
                proc_dir = Path(instance.pathFileSDF).parent.resolve()
            except Exception:
                proc_dir = None

        # Base permitida para remoção (proteção contra rm fora da raiz)
        processes_base = Path(
            getattr(settings, "PROCESSES_BASE_DIR",
                    Path(getattr(settings, "BASE_DIR")) / "files" / "processes")
        ).resolve()

        # Verifica se há outro processo apontando para a MESMA pasta; se houver, não remove
        should_delete_dir = False
        if proc_dir and proc_dir.exists():
            try:
                # só permite apagar se a pasta estiver DENTRO da base de processos
                if proc_dir == processes_base or proc_dir.is_relative_to(processes_base):
                    # procura outros processos usando um path dentro dessa pasta
                    from django.db.models import Q
                    siblings = Process.objects.filter(
                        ~Q(id=instance.id),
                        pathFileSDF__startswith=str(proc_dir)
                    ).exists()
                    should_delete_dir = not siblings
                else:
                    logger.warning("Skip delete: %s não está dentro de %s", proc_dir, processes_base)
            except Exception as e:
                logger.warning("Falha ao verificar pasta do processo: %s", e)

        # Deleta o registro do banco primeiro
        response = super().destroy(request, *args, **kwargs)

        # Depois tenta remover a pasta (para não bloquear a exclusão do registro)
        if should_delete_dir and proc_dir and proc_dir.exists():
            try:
                shutil.rmtree(proc_dir, ignore_errors=True)
                logger.info("Diretório do processo removido: %s", proc_dir)
            except Exception as e:
                logger.warning("Falha ao remover diretório do processo %s: %s", proc_dir, e)

        return response
