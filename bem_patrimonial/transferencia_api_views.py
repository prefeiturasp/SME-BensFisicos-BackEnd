from django_filters.rest_framework import DjangoFilterBackend
from django_filters import CharFilter, FilterSet, NumberFilter
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from bem_patrimonial.models import TransferenciaBemPatrimonial
from bem_patrimonial.transferencia_api_docs import (
    CREATE_TRANSFERENCIA_DOC,
    LIST_TRANSFERENCIAS_DOC,
    OPCOES_CADASTRO_TRANSFERENCIA_DOC,
    RETRIEVE_TRANSFERENCIA_DOC,
)
from bem_patrimonial.transferencia_api_serializers import (
    TransferenciaBemPatrimonialCreateSerializer,
    TransferenciaBemPatrimonialDetailSerializer,
    TransferenciaBemPatrimonialListSerializer,
    TransferenciaUoCadastroOptionSerializer,
    obter_ua_ponto_central,
    obter_uo_referencia_do_usuario,
    queryset_uos_destino_externas,
)
from dados_comuns.escopo import filtrar_queryset_transferencia_por_escopo


TRANSFERENCIA_ID_PATH_PARAM = OpenApiParameter(
    name="id",
    required=True,
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    description="Identificador numérico único da transferência.",
)


TRANSFERENCIA_LIST_QUERY_PARAMETERS = [
    OpenApiParameter(
        name="search",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description=(
            "Busca em: número NTBPM, número do processo, códigos/nomes/siglas "
            "das UOs de origem e destino, número patrimonial e nome dos bens."
        ),
    ),
    OpenApiParameter(
        name="ordering",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description=(
            "Ordenação por: id, numero_ntbpm, numero_processo, criado_em, "
            "atualizado_em, unidade_orcamentaria_origem__codigo e "
            "unidade_orcamentaria_destino__codigo. Use '-' para descendente."
        ),
    ),
    OpenApiParameter(
        name="page",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="Número da página.",
    ),
    OpenApiParameter(
        name="page_size",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="Quantidade de itens por página (máximo 100).",
    ),
    OpenApiParameter(
        name="numero_ntbpm",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="Filtra pelo número NTBPM.",
    ),
    OpenApiParameter(
        name="numero_processo",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="Filtra pelo número do processo.",
    ),
    OpenApiParameter(
        name="unidade_orcamentaria_origem",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="Filtra pela UO de origem.",
    ),
    OpenApiParameter(
        name="unidade_orcamentaria_destino",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="Filtra pela UO de destino.",
    ),
]


class TransferenciaBemPatrimonialPermission(IsAuthenticated):
    """
    Acesso ao módulo de Transferência:
    - apenas Gestor de Patrimônio autenticado, em linha com o Django Admin.
    """

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return bool(getattr(request.user, "is_gestor_patrimonio", False))

    def has_object_permission(self, request, view, obj):
        if not self.has_permission(request, view):
            return False

        queryset = TransferenciaBemPatrimonial.objects.filter(pk=obj.pk)
        return filtrar_queryset_transferencia_por_escopo(request.user, queryset).exists()


class TransferenciaBemPatrimonialFilter(FilterSet):
    numero_ntbpm = CharFilter(field_name="numero_ntbpm", lookup_expr="icontains")
    numero_processo = CharFilter(field_name="numero_processo", lookup_expr="icontains")
    unidade_orcamentaria_origem = NumberFilter(
        field_name="unidade_orcamentaria_origem__id"
    )
    unidade_orcamentaria_destino = NumberFilter(
        field_name="unidade_orcamentaria_destino__id"
    )

    class Meta:
        model = TransferenciaBemPatrimonial
        fields = [
            "numero_ntbpm",
            "numero_processo",
            "unidade_orcamentaria_origem",
            "unidade_orcamentaria_destino",
        ]
@extend_schema_view(
    list=extend_schema(
        tags=["Transferências"],
        summary="Listar transferências",
        description=LIST_TRANSFERENCIAS_DOC,
        parameters=TRANSFERENCIA_LIST_QUERY_PARAMETERS,
        responses={200: TransferenciaBemPatrimonialListSerializer(many=True)},
    ),
    retrieve=extend_schema(
        tags=["Transferências"],
        summary="Detalhar transferência",
        description=RETRIEVE_TRANSFERENCIA_DOC,
        parameters=[TRANSFERENCIA_ID_PATH_PARAM],
        responses={200: TransferenciaBemPatrimonialDetailSerializer},
    ),
    create=extend_schema(
        tags=["Transferências"],
        summary="Criar transferência",
        description=CREATE_TRANSFERENCIA_DOC,
        responses={
            201: TransferenciaBemPatrimonialDetailSerializer,
            400: OpenApiResponse(description="Erro de validação"),
            403: OpenApiResponse(description="Sem permissão"),
        },
    ),
)
class TransferenciaBemPatrimonialViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [TransferenciaBemPatrimonialPermission]
    http_method_names = ["get", "post", "head", "options"]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = TransferenciaBemPatrimonialFilter
    search_fields = (
        "numero_ntbpm",
        "numero_processo",
        "unidade_orcamentaria_origem__codigo",
        "unidade_orcamentaria_origem__nome",
        "unidade_orcamentaria_origem__sigla",
        "unidade_orcamentaria_destino__codigo",
        "unidade_orcamentaria_destino__nome",
        "unidade_orcamentaria_destino__sigla",
        "itens__bem__numero_patrimonial",
        "itens__bem__nome",
    )
    ordering_fields = [
        "id",
        "numero_ntbpm",
        "numero_processo",
        "criado_em",
        "atualizado_em",
        "unidade_orcamentaria_origem__codigo",
        "unidade_orcamentaria_destino__codigo",
    ]
    ordering = ["-criado_em"]

    def get_queryset(self):
        qs = (
            TransferenciaBemPatrimonial.objects.select_related(
                "unidade_orcamentaria_origem",
                "unidade_orcamentaria_destino",
                "unidade_administrativa_destino",
                "criado_por",
            )
            .prefetch_related("itens__bem", "itens__bem__unidade_administrativa")
        )
        return filtrar_queryset_transferencia_por_escopo(self.request.user, qs).distinct()

    def get_serializer_class(self):
        if self.action == "list":
            return TransferenciaBemPatrimonialListSerializer
        if self.action == "create":
            return TransferenciaBemPatrimonialCreateSerializer
        return TransferenciaBemPatrimonialDetailSerializer

    def _detail_response(self, transferencia, request, http_status=status.HTTP_200_OK):
        serializer = TransferenciaBemPatrimonialDetailSerializer(
            transferencia,
            context={"request": request},
        )
        return Response(serializer.data, status=http_status)

    @extend_schema(
        tags=["Transferências"],
        summary="Listar opções de destino",
        description=OPCOES_CADASTRO_TRANSFERENCIA_DOC,
        request=None,
        responses={200: TransferenciaUoCadastroOptionSerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="opcoes-cadastro")
    def opcoes_cadastro(self, request):
        uo_origem = obter_uo_referencia_do_usuario(request.user)
        uos = queryset_uos_destino_externas(getattr(uo_origem, "pk", None))
        data = [
            {
                "id": uo.id,
                "codigo": uo.codigo,
                "nome": uo.nome,
                "label": f"{uo.codigo} - {uo.nome}",
                "tem_ponto_central": bool(obter_ua_ponto_central(uo)),
            }
            for uo in uos
        ]
        serializer = TransferenciaUoCadastroOptionSerializer(data, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        transferencia = serializer.save()
        return self._detail_response(transferencia, request, http_status=status.HTTP_201_CREATED)
