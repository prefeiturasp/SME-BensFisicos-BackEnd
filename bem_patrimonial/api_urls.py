from rest_framework.routers import DefaultRouter

from bem_patrimonial.api_views import BaixaFisicaBemPatrimonialViewSet

router = DefaultRouter()
router.register(
    r"",
    BaixaFisicaBemPatrimonialViewSet,
    basename="baixas-fisicas",
)

urlpatterns = router.urls
