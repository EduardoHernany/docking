# macromolecules/admin.py
from django.contrib import admin
from .models import MacromoleculeType, Macromolecule


@admin.register(MacromoleculeType)
class MacromoleculeTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "active", "created_at", "updated_at")
    list_filter = ("active",)
    search_fields = ("name",)
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(Macromolecule)
class MacromoleculeAdmin(admin.ModelAdmin):
    list_display = (
        "nome", "type",
        "rmsd_redocking", "energia_original",
        "created_at",
    )
    list_filter = ["type"]
    search_fields = ("nome", "rec", "ligante_original")
    ordering = ("-created_at",)
    autocomplete_fields = ("type",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {
            "fields": ("nome", "rec", "type", )
        }),
        ("Configuração de Grid", {
            "fields": ("gridsize", "gridcenter"),
            "classes": ("collapse",)
        }),
        ("Ligante / Resultados", {
            "fields": ("ligante_original", "rmsd_redocking", "energia_original", "pathFilefld"),
            "classes": ("collapse",)
        }),
        ("Metadados", {
            "fields": ("created_at", "updated_at"),
        }),
    )
