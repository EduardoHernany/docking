# djangoAPI/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework.renderers import JSONRenderer

from users.views_auth import AuthLoginPasswordView, AuthLoginProfileView
from users.views_password import PasswordRecoveryView, PasswordUpdateView

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/openapi.json",
        SpectacularAPIView.as_view(
            renderer_classes=[JSONRenderer],  
        ),
        name="schema",
    ),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),

     # Auth (JWT)
     path("api/auth/login/password", AuthLoginPasswordView.as_view(), name="auth-login-password"),
    path("api/auth/login/profile", AuthLoginProfileView.as_view(), name="auth-login-profile"),
    path("api/auth/password/recovery", PasswordRecoveryView.as_view(), name="auth-password-recovery"),
    path("api/auth/password/update", PasswordUpdateView.as_view(), name="auth-password-update"),

    # rotas dos apps
    path("api/", include("users.urls")),
    path("api/", include("macromolecules.urls")),
    path("api/", include("processes.urls")),
]

