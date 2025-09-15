import logging
import os
from pathlib import Path
from django.conf import settings
from django.utils.text import slugify
from rest_framework import serializers

from macromolecules.tasks import prepare_macromolecule
from .models import MacromoleculeType, Macromolecule


class MacromoleculeTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MacromoleculeType
        fields = [
            "id",
            "name",
            "description",
            "redocking",          # ← novo no serializer do TYPE
            "active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MacromoleculeReadTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MacromoleculeType
        fields = ["id", "name", "redocking"]     # útil na leitura


class MacromoleculeSerializer(serializers.ModelSerializer):
    # leitura completa
    type_detail = MacromoleculeReadTypeSerializer(source="type", read_only=True)

    class Meta:
        model = Macromolecule
        fields = [
            "id",
            "nome",
            "rec",
            "type",
            "type_detail",
            # "redocking",  ← REMOVIDO (agora pertence ao TYPE)
            "gridsize",
            "gridcenter",
            "ligante_original",
            "rmsd_redocking",
            "energia_original",
            "pathFilefld",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MacromoleculeCreateSerializer(serializers.ModelSerializer):
    """
    Serializer usado apenas no POST com upload.
    `redocking` agora vem de MacromoleculeType.redocking.
    """
    type = serializers.PrimaryKeyRelatedField(queryset=MacromoleculeType.objects.all())
    recptorFile = serializers.FileField(write_only=True)
    ligandFile = serializers.FileField(write_only=True)

    class Meta:
        model = Macromolecule
        fields = [
            "nome",
            "type",
            "gridsize",
            "gridcenter",
            "recptorFile",
            "ligandFile",
        ]

    def create(self, validated_data):
        rec_file = validated_data.pop("recptorFile")
        lig_file = validated_data.pop("ligandFile")
        mtype: MacromoleculeType = validated_data["type"]

        # nomes “seguros” para diretórios
        type_name = slugify(mtype.name, allow_unicode=False) or "tipo"
        redocking_str = "true" if mtype.redocking else "false"

        # Nomes originais (com extensão) e "stem" para salvar no DB
        rec_name  = Path(rec_file.name).name           # ex.: "1cjb_a.pdb"
        rec_stem  = Path(rec_name).stem                # ex.: "1cjb_a"   ← salvar no DB
        lig_name  = Path(lig_file.name).name           # ex.: "POP.pdb"
        lig_stem  = Path(lig_name).stem                # ex.: "POP"      ← salvar no DB

        # Diretório baseado no stem do receptor (sem extensão)
        rec_dirname = slugify(rec_stem, allow_unicode=False) or "receptor"

        # destino: <BASE>/molecules/<type.name>/<redocking>/<rec_stem>
        base_dir: Path = settings.MOLECULES_BASE_DIR
        base_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(base_dir, 0o2775)
        except PermissionError:
            pass

        dest_dir = base_dir / type_name / redocking_str / rec_dirname
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(dest_dir, 0o2775)
        except PermissionError:
            raise serializers.ValidationError({
                "storage": "Sem permissão para escrever em MOLECULES_BASE_DIR. "
                           "Ajuste as permissões do volume /app/files/molecules."
            })

        # === Salva os arquivos no disco COM extensão ===
        rec_path = dest_dir / rec_name
        lig_path = dest_dir / lig_name

        with rec_path.open("wb") as f:
            for chunk in rec_file.chunks():
                f.write(chunk)
        with lig_path.open("wb") as f:
            for chunk in lig_file.chunks():
                f.write(chunk)

        # === Preenche campos do modelo (SEM extensão no banco) ===
        validated_data["rec"] = rec_stem
        validated_data["ligante_original"] = lig_stem
        validated_data["pathFilefld"] = str(dest_dir)

        instance = Macromolecule.objects.create(**validated_data)

        # === Enfileira a task passando os NOMES COM EXTENSÃO ===
        try:
            prepare_macromolecule.delay(
                str(dest_dir),
                rec_name,                              # com extensão
                validated_data.get("gridsize"),
                validated_data.get("gridcenter"),
                lig_name if mtype.redocking else None, # com extensão (se redocking)
                str(instance.id),
            )
        except Exception:
            logging.getLogger(__name__).exception("Falha ao enfileirar task prepare_macromolecule")

        return instance