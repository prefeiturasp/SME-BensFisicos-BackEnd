from rest_framework.routers import DefaultRouter
from bem_patrimonial.nbbpm_api_views import NBBPMViewSet

router = DefaultRouter()
router.register(r"", NBBPMViewSet, basename="nbbpm")

urlpatterns = router.urls
