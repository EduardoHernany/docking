# processes/urls.py
from rest_framework.routers import DefaultRouter
from .views import ProcessViewSet

router = DefaultRouter()
router.register(r"processes", ProcessViewSet, basename="process")

urlpatterns = router.urls
