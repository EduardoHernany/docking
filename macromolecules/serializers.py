# macromolecules/serializers.py
from pathlib import Path
from django.conf import settings
from django.utils.text import slugify
from rest_framework import serializers

from .models import MacromoleculeType, Macromolecule


class MacromoleculeTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MacromoleculeType
        fields = [
            "id",
            "name",
            "description",
            "active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MacromoleculeReadTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MacromoleculeType
        fields = ["id", "name"]


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
            "redocking",
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
    """
    type = serializers.PrimaryKeyRelatedField(queryset=MacromoleculeType.objects.all())
    recptorFile = serializers.FileField(write_only=True)
    ligandFile = serializers.FileField(write_only=True)

    class Meta:
        model = Macromolecule
        fields = [
            "nome",
            "type",
            "redocking",
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
        redocking_str = "true" if validated_data.get("redocking", True) else "false"
        rec_filename = Path(rec_file.name).name
        rec_dirname = slugify(rec_filename, allow_unicode=False) or "receptor"

        # destino: <BASE>/molecules/<type.name>/<redocking>/<recptorFile.filename>/arquivos recebidos
        base_dir: Path = settings.MOLECULES_BASE_DIR
        dest_dir = base_dir / type_name / redocking_str / rec_dirname
        dest_dir.mkdir(parents=True, exist_ok=True)

        # caminhos finais
        rec_path = dest_dir / rec_filename
        lig_filename = Path(lig_file.name).name
        lig_path = dest_dir / lig_filename

        # grava os arquivos (streaming)
        with rec_path.open("wb") as f:
            for chunk in rec_file.chunks():
                f.write(chunk)
        with lig_path.open("wb") as f:
            for chunk in lig_file.chunks():
                f.write(chunk)

        # preencher campos do modelo
        validated_data["rec"] = rec_filename
        validated_data["ligante_original"] = lig_filename
        validated_data["pathFilefld"] = str(dest_dir)

        instance = Macromolecule.objects.create(**validated_data)
        return instance
