# macromolecules/urls.py
from rest_framework.routers import DefaultRouter
from .views import MacromoleculeTypeViewSet, MacromoleculeViewSet

router = DefaultRouter()
router.register(r"macromolecule-types", MacromoleculeTypeViewSet, basename="macromolecule-type")
router.register(r"macromolecules", MacromoleculeViewSet, basename="macromolecule")

urlpatterns = router.urls
