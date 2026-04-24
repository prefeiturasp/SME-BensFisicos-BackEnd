from rest_framework.routers import DefaultRouter

from dados_comuns.api_views import (
    UnidadeAdministrativaViewSet,
    UnidadeOrcamentariaViewSet,
)

router = DefaultRouter()
router.register(
    r"unidades-orcamentarias",
    UnidadeOrcamentariaViewSet,
    basename="unidades-orcamentarias",
)
router.register(
    r"unidades-administrativas",
    UnidadeAdministrativaViewSet,
    basename="unidades-administrativas",
)

urlpatterns = router.urls
