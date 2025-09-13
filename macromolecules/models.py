# macromolecules/models.py
import uuid
from django.db import models


class MacromoleculeType(models.Model):
    """Tabela dinâmica para tipos de macromolécula (substitui o Enum)."""
    class Meta:
        db_table = "macromolecule_types"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)   # ex.: 'falciparum'
    description = models.TextField(null=True, blank=True)
    active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Macromolecule(models.Model):
    class Meta:
        db_table = "macromolecules"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nome = models.CharField(max_length=255)
    rec = models.CharField(max_length=255)

    # FK dinâmica para o tipo
    type = models.ForeignKey(
        MacromoleculeType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="macromolecules",
    )

    redocking = models.BooleanField(default=True)
    gridsize = models.CharField(max_length=255, null=True, blank=True)
    gridcenter = models.CharField(max_length=255, null=True, blank=True)
    ligante_original = models.CharField(max_length=255, null=True, blank=True)
    rmsd_redocking = models.CharField(max_length=255, null=True, blank=True)
    energia_original = models.CharField(max_length=255, null=True, blank=True)
    pathFilefld = models.CharField(max_length=1024, null=True, blank=True)  # mantém o nome original

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nome
