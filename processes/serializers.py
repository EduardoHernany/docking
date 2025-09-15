# processes/serializers.py
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils.text import slugify
from pathlib import Path
from rest_framework import serializers
from django.db import transaction
from .models import Process
from macromolecules.models import MacromoleculeType

User = get_user_model()

class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name"]


class MacromoleculeTypeMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = MacromoleculeType
        fields = ["id", "name"]


class ProcessSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    type = serializers.PrimaryKeyRelatedField(queryset=MacromoleculeType.objects.all())
    user_detail = UserMiniSerializer(source="user", read_only=True)
    type_detail = MacromoleculeTypeMiniSerializer(source="type", read_only=True)

    class Meta:
        model = Process
        fields = [
            "id",
            "nome",
            "type",
            "type_detail",
            "status",
            "resultado_final",
            "pathFileSDF",
            "pathFileZIP",        # ⬅ adicionar
            "user",
            "user_detail",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "pathFileZIP"]


class ProcessCreateSerializer(serializers.ModelSerializer):
    type = serializers.PrimaryKeyRelatedField(queryset=MacromoleculeType.objects.all())
    sdfFile = serializers.FileField(write_only=True)

    class Meta:
        model = Process
        fields = ["nome", "type", "sdfFile"]

    @transaction.atomic
    def create(self, validated_data):
        sdf_file = validated_data.pop("sdfFile")
        mtype: MacromoleculeType = validated_data["type"]

        # O user chega via serializer.save(user=...) (ver perform_create no ViewSet)
        user = validated_data.get("user")
        if user is None:
            # fallback: tenta contexto
            req = self.context.get("request")
            user = getattr(req, "user", None)
        if user is None or not getattr(user, "id", None):
            raise serializers.ValidationError("Usuário não identificado para montar o caminho do processo.")

        # Bases: files/molecules e files/processes (com defaults)
        molecules_base: Path = getattr(
            settings, "MOLECULES_BASE_DIR", Path(settings.BASE_DIR) / "files" / "molecules"
        )
        files_root = molecules_base.parent  # "<BASE>/files"
        proc_base: Path = getattr(settings, "PROCESSES_BASE_DIR", files_root / "processes")

        # 1) Cria o Process primeiro (sem pathFileSDF) para obter o ID
        instance = Process.objects.create(**validated_data)

        # Slugs seguros
        user_slug = slugify(f"{getattr(user, 'username', 'user')}-{user.id}", allow_unicode=False) or f"user-{user.id}"
        proc_slug = slugify(f"{validated_data.get('nome') or 'processo'}-{instance.id}", allow_unicode=False) or f"processo-{instance.id}"

        # 2) Monta diretório final: files/processes/<User.name-ID>/<process.name-ID>/
        dest_dir = proc_base / user_slug / proc_slug
        dest_dir.mkdir(parents=True, exist_ok=True)

        # (Opcional) setgid e permissões amigáveis para grupo
        try:
            for d in [proc_base, proc_base / user_slug, dest_dir]:
                d.mkdir(parents=True, exist_ok=True)
                d.chmod(0o2775)
        except PermissionError:
            pass

        # 3) Grava o arquivo no destino
        sdf_name = Path(sdf_file.name).name
        dest_path = dest_dir / sdf_name
        with dest_path.open("wb") as f:
            for chunk in sdf_file.chunks():
                f.write(chunk)

        # 4) Atualiza o path no Process
        instance.pathFileSDF = str(dest_path)
        instance.save(update_fields=["pathFileSDF"])

        return instance
