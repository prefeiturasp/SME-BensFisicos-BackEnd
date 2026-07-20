from rest_framework.routers import DefaultRouter

from bem_patrimonial.transferencia_api_views import TransferenciaBemPatrimonialViewSet

router = DefaultRouter()
router.register(
    r"",
    TransferenciaBemPatrimonialViewSet,
    basename="transferencias",
)

urlpatterns = router.urls
