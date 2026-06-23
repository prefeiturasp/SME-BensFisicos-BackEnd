from django.urls import path
from rest_framework.routers import DefaultRouter

from inventario.api_views import (
    ConciliacaoUAViewSet,
    ItemConciliacaoViewSet,
    ParametroConciliacaoAnualViewSet,
)

router = DefaultRouter()
router.register(
    r"inventario/parametros-conciliacao-anual",
    ParametroConciliacaoAnualViewSet,
    basename="parametros-conciliacao-anual",
)
router.register(
    r"inventario/conciliacoes",
    ConciliacaoUAViewSet,
    basename="conciliacoes",
)


item_list = ItemConciliacaoViewSet.as_view({
    "get": "list",
})
item_detail = ItemConciliacaoViewSet.as_view({
    "get": "retrieve",
})
item_situacoes = ItemConciliacaoViewSet.as_view({
    "get": "situacoes_disponiveis",
})
item_registrar_ocorrencia = ItemConciliacaoViewSet.as_view({
    "post": "registrar_ocorrencia",
})
item_excluir_ocorrencia = ItemConciliacaoViewSet.as_view({
    "post": "excluir_ocorrencia",
})
item_historico = ItemConciliacaoViewSet.as_view({
    "get": "historico",
})

urlpatterns = router.urls + [
    path(
        "inventario/conciliacoes/<int:conciliacao_pk>/itens/",
        item_list,
        name="itens-conciliacao-list",
    ),
    path(
        "inventario/conciliacoes/<int:conciliacao_pk>/itens/<int:item_id>/",
        item_detail,
        name="itens-conciliacao-detail",
    ),
    path(
        "inventario/conciliacoes/<int:conciliacao_pk>/itens/<int:item_id>/situacoes-disponiveis/",
        item_situacoes,
        name="itens-conciliacao-situacoes-disponiveis",
    ),
    path(
        "inventario/conciliacoes/<int:conciliacao_pk>/itens/<int:item_id>/ocorrencias/",
        item_registrar_ocorrencia,
        name="itens-conciliacao-registrar-ocorrencia",
    ),
    path(
        "inventario/conciliacoes/<int:conciliacao_pk>/itens/<int:item_id>/ocorrencias/remover/",
        item_excluir_ocorrencia,
        name="itens-conciliacao-excluir-ocorrencia",
    ),
    path(
        "inventario/conciliacoes/<int:conciliacao_pk>/itens/<int:item_id>/historico/",
        item_historico,
        name="itens-conciliacao-historico",
    ),
]
