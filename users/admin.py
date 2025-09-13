# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username","email","first_name","last_name","role","is_active","deleted","is_staff")
    list_filter = ("role","deleted","is_active","is_staff","is_superuser","groups")
    search_fields = ("username","email","first_name","last_name")
    ordering = ("username",)
    fieldsets = BaseUserAdmin.fieldsets + (("Extras", {"fields": ("role","deleted")}),)
    add_fieldsets = BaseUserAdmin.add_fieldsets + ((None, {"fields": ("role","deleted")}),)
