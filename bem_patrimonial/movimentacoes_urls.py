from rest_framework.routers import DefaultRouter

from bem_patrimonial.movimentacao_api_views import MovimentacaoBemPatrimonialViewSet

router = DefaultRouter()
router.register(
    r"movimentacoes",
    MovimentacaoBemPatrimonialViewSet,
    basename="movimentacoes",
)

urlpatterns = router.urls
