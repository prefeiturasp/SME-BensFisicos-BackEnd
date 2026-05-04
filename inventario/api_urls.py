from rest_framework.routers import DefaultRouter

from inventario.api_views import ParametroConciliacaoAnualViewSet

router = DefaultRouter()
router.register(
    r"inventario/parametros-conciliacao-anual",
    ParametroConciliacaoAnualViewSet,
    basename="parametros-conciliacao-anual",
)

urlpatterns = router.urls
