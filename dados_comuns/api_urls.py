from rest_framework.routers import DefaultRouter

from dados_comuns.api_views import UnidadeAdministrativaViewSet

router = DefaultRouter()
router.register(
    r"unidades-administrativas",
    UnidadeAdministrativaViewSet,
    basename="unidades-administrativas",
)

urlpatterns = router.urls
