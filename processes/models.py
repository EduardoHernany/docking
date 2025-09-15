import uuid
from django.db import models
from users.models import User
from macromolecules.models import MacromoleculeType


class ProcessStatusEnum(models.TextChoices):
    EM_FILA     = "EM_FILA", "EM_FILA"
    PROCESSANDO = "PROCESSANDO", "PROCESSANDO"
    CONCLUIDO   = "CONCLUIDO", "CONCLUIDO"
    ERROR       = "ERROR", "ERROR"


class Process(models.Model):
    class Meta:
        db_table = "processes"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(max_length=255)

    # referencia o tipo (que agora contém redocking) e o usuário
    type = models.ForeignKey(
        MacromoleculeType,
        on_delete=models.PROTECT,
        related_name="processes",
    )

    status = models.CharField(
        max_length=20,
        choices=ProcessStatusEnum.choices,
        default=ProcessStatusEnum.EM_FILA,
    )

    resultado_final = models.JSONField(null=True, blank=True)  # JSONB
    pathFileSDF = models.CharField(max_length=1024, null=True, blank=True)

    # ⬇⬇⬇ NOVO: caminho absoluto do .zip gerado
    pathFileZIP = models.CharField(max_length=1024, null=True, blank=True)
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="processes",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.nome} ({self.status})"
