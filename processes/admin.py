# processes/admin.py
from django.contrib import admin
from .models import Process


@admin.register(Process)
class ProcessAdmin(admin.ModelAdmin):
    list_display = ("nome", "type", "user", "status", "created_at")
    list_filter = ("status", "type")
    search_fields = ("nome", "user__username", "user__email", "type__name")
    ordering = ("-created_at",)
    autocomplete_fields = ("type", "user")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (None, {
            "fields": ("nome", "type", "user", "status")
        }),
        ("Resultado", {
            "fields": ("resultado_final", "pathFileSDF"),
            "classes": ("collapse",)
        }),
        ("Metadados", {
            "fields": ("created_at", "updated_at"),
        }),
    )
