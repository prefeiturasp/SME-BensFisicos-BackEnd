from collections import defaultdict

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse

from django_filters.rest_framework import DjangoFilterBackend
import django_filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import (
    NotFound,
    ValidationError as DRFValidationError,
)
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from dados_comuns.context import audit_as
from dados_comuns.escopo import filtrar_queryset_por_escopo
from dados_comuns.models import HistoricoGeral

from inventario.api_serializers import (
    ConciliacaoExportQuerySerializer,
    ConciliacaoHistoricoGrupoSerializer,
    ConciliacaoUACreateSerializer,
    ConciliacaoUADetailSerializer,
    ConciliacaoUAListSerializer,
    ItemConciliacaoDetailSerializer,
    ItemConciliacaoListSerializer,
    ParametroConciliacaoAnualDetailSerializer,
    ParametroConciliacaoAnualListSerializer,
    RegistrarOcorrenciaSerializer,
)
from inventario.conciliacao import excluir_ocorrencia, registrar_ocorrencia
from inventario import constants
from inventario.models import (
    ConciliacaoUA,
    ItemConciliacao,
    ParametroConciliacaoAnual,
)
from inventario.permissions import ConciliacaoUAPermission, ItemConciliacaoPermission
from inventario.relatorio_conciliacao_pdf import gerar_pdf_conciliacao
from inventario.utils_conciliacao.conciliacao_automatica import (
    processar_conciliacao_anual_automatica,
)
from inventario.utils_conciliacao.conciliacao_utils import (
    criar_itens_conciliacao,
    finalizar_conciliacao,
    remover_itens_baixados_invalidos,
)


class ParametroConciliacaoAnualPermission(BasePermission):
    def _pode_acessar_modulo(self, user):
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return bool(getattr(user, "is_gestor_patrimonio", False))

    def _pode_gerenciar(self, user):
        return bool(
            getattr(user, "is_superuser", False)
            or getattr(user, "is_gestor_patrimonio", False)
        )

    def has_permission(self, request, view):
        if not self._pode_acessar_modulo(request.user):
            return False

        action = getattr(view, "action", None)
        if action in ("list", "retrieve"):
            return True

        if action in ("create", "update", "partial_update", "destroy"):
            return self._pode_gerenciar(request.user)

        return self._pode_gerenciar(request.user)

    def has_object_permission(self, request, view, obj):
        action = getattr(view, "action", None)
        if action == "retrieve":
            return True

        if action in ("update", "partial_update", "destroy"):
            return self._pode_gerenciar(request.user)

        return True


@extend_schema_view(
    list=extend_schema(
        tags=["Inventário"],
        summary="Listar parâmetros de conciliação anual",
        description=(
            "Lista paginada com busca, filtros e ordenação. "
            "Acesso restrito a superusuário e gestor de patrimônio."
        ),
    ),
    retrieve=extend_schema(
        tags=["Inventário"],
        summary="Detalhar parâmetro de conciliação anual",
    ),
    create=extend_schema(
        tags=["Inventário"],
        summary="Criar parâmetro de conciliação anual",
    ),
    update=extend_schema(
        tags=["Inventário"],
        summary="Atualizar parâmetro de conciliação anual",
    ),
    partial_update=extend_schema(
        tags=["Inventário"],
        summary="Atualizar parcialmente parâmetro de conciliação anual",
    ),
    destroy=extend_schema(
        tags=["Inventário"],
        summary="Excluir parâmetro de conciliação anual",
    ),
)
class ParametroConciliacaoAnualViewSet(viewsets.ModelViewSet):
    permission_classes = [ParametroConciliacaoAnualPermission]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["ativo", "ano_referencia"]
    search_fields = [
        "ano_referencia",
        "unidade_orcamentaria__codigo",
        "unidade_orcamentaria__sigla",
        "unidade_orcamentaria__nome",
    ]
    ordering_fields = [
        "id",
        "ano_referencia",
        "periodo_inicial",
        "periodo_final",
        "ativo",
        "unidade_orcamentaria__codigo",
    ]
    ordering = ["-ano_referencia", "-periodo_inicial", "unidade_orcamentaria__codigo"]

    def get_serializer_class(self):
        if self.action == "list":
            return ParametroConciliacaoAnualListSerializer
        return ParametroConciliacaoAnualDetailSerializer

    def get_queryset(self):
        qs = ParametroConciliacaoAnual.objects.select_related("unidade_orcamentaria")

        user = self.request.user
        uo_id = getattr(user, "unidade_orcamentaria_id", None)
        if uo_id:
            return qs.filter(unidade_orcamentaria_id=uo_id)

        return qs.none()

    def get_object(self):
        obj = super().get_object()
        if not self._pode_acessar_objeto(self.request.user, obj):
            raise NotFound()
        return obj

    def _pode_acessar_objeto(self, user, obj):
        user_uo_id = getattr(user, "unidade_orcamentaria_id", None)
        if user_uo_id:
            return obj.unidade_orcamentaria_id == user_uo_id
        return False

    def _validate_uo_scope(self, validated_data, instance=None):
        user = self.request.user

        nova_uo = validated_data.get("unidade_orcamentaria")

        if instance is not None and nova_uo is not None:
            if nova_uo != instance.unidade_orcamentaria:
                raise DRFValidationError(
                    {
                        "unidade_orcamentaria": (
                            "A Unidade Orçamentária não pode ser alterada."
                        )
                    }
                )

        if instance is not None and nova_uo is None:
            nova_uo = instance.unidade_orcamentaria

        if nova_uo is None:
            raise DRFValidationError(
                {"unidade_orcamentaria": "Unidade Orçamentária é obrigatória."}
            )

        user_uo = getattr(user, "unidade_orcamentaria", None)
        if user_uo is None or nova_uo != user_uo:
            raise DRFValidationError(
                {
                    "unidade_orcamentaria": (
                        "Você não pode gerenciar parâmetros de outra "
                        "Unidade Orçamentária."
                    )
                }
            )

    def _raise_drf_validation_error(self, exc):
        if hasattr(exc, "message_dict"):
            errors = dict(exc.message_dict)
            if "__all__" in errors:
                errors["non_field_errors"] = errors.pop("__all__")
            raise DRFValidationError(errors)

        if hasattr(exc, "messages"):
            raise DRFValidationError({"non_field_errors": exc.messages})

        raise DRFValidationError({"non_field_errors": [str(exc)]})

    def perform_create(self, serializer):
        self._validate_uo_scope(serializer.validated_data)
        try:
            serializer.save()
        except DjangoValidationError as exc:
            self._raise_drf_validation_error(exc)

    def perform_update(self, serializer):
        self._validate_uo_scope(
            serializer.validated_data,
            instance=serializer.instance,
        )
        try:
            serializer.save()
        except DjangoValidationError as exc:
            self._raise_drf_validation_error(exc)

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise DRFValidationError(
                {
                    "detail": (
                        "Não foi possível excluir este parâmetro porque "
                        "existem vínculos ativos no sistema."
                    )
                }
            )


CONCILIACAO_ID_PATH_PARAM = OpenApiParameter(
    name="id",
    required=True,
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    description="Identificador numérico único da conciliação.",
)

CONCILIACAO_NESTED_ID_PATH_PARAM = OpenApiParameter(
    name="conciliacao_pk",
    required=True,
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    description="Identificador numérico único da conciliação pai.",
)

ITEM_CONCILIACAO_ID_PATH_PARAM = OpenApiParameter(
    name="item_id",
    required=True,
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    description="Identificador numérico único do item de conciliação.",
)

CONCILIACAO_LIST_QUERY_PARAMETERS = [
    OpenApiParameter(
        name="search",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description=(
            "Busca em: número da conciliação, código/nome/sigla da Unidade "
            "Administrativa."
        ),
    ),
    OpenApiParameter(
        name="ordering",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description=(
            "Ordenação por: id, criado_em, periodo_final, status, tipo, "
            "unidade_administrativa__codigo, unidade_administrativa__sigla, "
            "unidade_administrativa__nome. Use '-' para descendente."
        ),
    ),
    OpenApiParameter(
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=[c[0] for c in constants.STATUS_CONCILIACAO],
        description=(
            "Filtra por status da conciliação. Aceita um valor ou vários "
            "separados por vírgula."
        ),
    ),
    OpenApiParameter(
        name="tipo",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=[c[0] for c in constants.TIPOS_CONCILIACAO],
        description="Filtra por tipo da conciliação.",
    ),
    OpenApiParameter(
        name="unidade_administrativa",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="Filtra por Unidade Administrativa (ID).",
    ),
    OpenApiParameter(
        name="ano_vigencia",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="Filtra pelo ano de vigência (ano do período final).",
    ),
    OpenApiParameter(
        name="periodo_final__gte",
        type=OpenApiTypes.DATE,
        location=OpenApiParameter.QUERY,
        description="Filtra conciliações com período final a partir da data (YYYY-MM-DD).",
    ),
    OpenApiParameter(
        name="periodo_final__lte",
        type=OpenApiTypes.DATE,
        location=OpenApiParameter.QUERY,
        description="Filtra conciliações com período final até a data (YYYY-MM-DD).",
    ),
    OpenApiParameter(
        name="criado_em__gte",
        type=OpenApiTypes.DATETIME,
        location=OpenApiParameter.QUERY,
        description="Filtra conciliações criadas a partir da data/hora informada.",
    ),
    OpenApiParameter(
        name="criado_em__lte",
        type=OpenApiTypes.DATETIME,
        location=OpenApiParameter.QUERY,
        description="Filtra conciliações criadas até a data/hora informada.",
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
]

ITEM_LIST_QUERY_PARAMETERS = [
    OpenApiParameter(
        name="search",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description=(
            "Busca em: número patrimonial e nome do bem."
        ),
    ),
    OpenApiParameter(
        name="ordering",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description=(
            "Ordenação por: id, atualizado_em, situacao, "
            "bem__numero_patrimonial, bem__nome. Use '-' para descendente."
        ),
    ),
    OpenApiParameter(
        name="situacao",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        enum=[c[0] for c in constants.SITUACOES_ITEM_CONCILIACAO],
        description=(
            "Filtra por situação do item. Aceita um valor ou vários separados "
            "por vírgula (ex.: divergente,nao_encontrado)."
        ),
    ),
    OpenApiParameter(
        name="tem_ocorrencia",
        type=OpenApiTypes.BOOL,
        location=OpenApiParameter.QUERY,
        description="Filtra itens com (true) ou sem (false) ocorrência registrada.",
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
]


def _filtrar_ano_vigencia(queryset, value):
    if not value:
        return queryset
    try:
        ano = int(value)
    except (TypeError, ValueError):
        return queryset
    return queryset.filter(periodo_final__year=ano)


class ConciliacaoUAFilter(django_filters.FilterSet):
    """
    FilterSet customizado para ConciliacaoUA.

    Suporta:
    - status: filtro exato ou lista (via valores separados por vírgula)
    - tipo: filtro exato
    - unidade_administrativa: filtro por ID
    - periodo_final__gte / periodo_final__lte: range de período final
    - criado_em__gte / criado_em__lte: range de data de criação
    """

    status = django_filters.CharFilter(method="filter_status")
    periodo_final__gte = django_filters.DateFilter(
        field_name="periodo_final", lookup_expr="gte"
    )
    periodo_final__lte = django_filters.DateFilter(
        field_name="periodo_final", lookup_expr="lte"
    )
    criado_em__gte = django_filters.DateTimeFilter(
        field_name="criado_em", lookup_expr="gte"
    )
    criado_em__lte = django_filters.DateTimeFilter(
        field_name="criado_em", lookup_expr="lte"
    )

    class Meta:
        model = ConciliacaoUA
        fields = ["tipo", "unidade_administrativa"]

    def filter_status(self, queryset, name, value):
        if not value:
            return queryset
        valores = [v.strip() for v in value.split(",") if v.strip()]
        if len(valores) == 1:
            return queryset.filter(status=valores[0])
        return queryset.filter(status__in=valores)


class ItemConciliacaoFilter(django_filters.FilterSet):
    """
    FilterSet customizado para ItemConciliacao.

    Suporta:
    - situacao: filtro exato ou lista (via valores separados por vírgula)
    """

    situacao = django_filters.CharFilter(method="filter_situacao")

    class Meta:
        model = ItemConciliacao
        fields = ["situacao"]

    def filter_situacao(self, queryset, name, value):
        if not value:
            return queryset
        valores = [v.strip() for v in value.split(",") if v.strip()]
        if not valores:
            return queryset
        valores_validos = {c[0] for c in constants.SITUACOES_ITEM_CONCILIACAO}
        invalidos = [v for v in valores if v not in valores_validos]
        if invalidos:
            raise DRFValidationError(
                {"situacao": f"Valor(es) inválido(s): {', '.join(invalidos)}"}
            )
        return queryset.filter(situacao__in=valores)


class AuditHistoryConciliacaoMixin:
    audit_model = None
    historico_grupo_serializer_class = None

    def _get_audit_content_type(self):
        return ContentType.objects.get_for_model(self.audit_model)

    def _registrar_historico(
        self, obj, campo, valor_antigo, valor_novo, usuario, justificativa=""
    ):
        ct = self._get_audit_content_type()
        HistoricoGeral.objects.create(
            content_type=ct,
            object_id=str(obj.pk),
            campo=campo,
            valor_antigo=str(valor_antigo) if valor_antigo is not None else "",
            valor_novo=str(valor_novo) if valor_novo is not None else "",
            alterado_por=usuario,
            justificativa=justificativa,
        )

    def _build_historico_response(self, instance):
        historicos = (
            HistoricoGeral.objects.filter(
                content_type=self._get_audit_content_type(),
                object_id=str(instance.pk),
            )
            .select_related("alterado_por")
            .order_by("-alterado_em")
        )

        agrupado = defaultdict(list)
        for item in historicos:
            chave = (item.alterado_em.replace(microsecond=0), item.alterado_por_id)
            agrupado[chave].append(item)

        resposta = []
        for (alterado_em, alterado_por_id), itens in agrupado.items():
            resposta.append(
                {
                    "alterado_em": alterado_em,
                    "alterado_por": alterado_por_id,
                    "alterado_por_nome": (
                        itens[0].alterado_por.nome if itens[0].alterado_por else None
                    ),
                    "acoes": [
                        {
                            "campo": i.campo,
                            "valor_antigo": i.valor_antigo,
                            "valor_novo": i.valor_novo,
                            "justificativa": i.justificativa,
                        }
                        for i in itens
                    ],
                }
            )

        resposta_ordenada = sorted(
            resposta,
            key=lambda row: row["alterado_em"],
            reverse=True,
        )

        serializer = self.historico_grupo_serializer_class(
            resposta_ordenada,
            many=True,
        )
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        tags=["Inventário"],
        summary="Listar conciliações",
        description=(
            "Lista paginada com busca, filtros e ordenação. O escopo é "
            "automaticamente restrito à Unidade Administrativa do usuário "
            "(operador/gestor com UA) ou à Unidade Orçamentária do gestor."
        ),
        parameters=CONCILIACAO_LIST_QUERY_PARAMETERS,
        responses={
            200: OpenApiResponse(description="Lista retornada com sucesso."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(
                description="Usuário sem permissão para acessar o recurso."
            ),
        },
    ),
    retrieve=extend_schema(
        tags=["Inventário"],
        summary="Detalhar conciliação",
        parameters=[CONCILIACAO_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(description="Detalhe retornado com sucesso."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão."),
            404: OpenApiResponse(description="Conciliação não encontrada."),
        },
    ),
    create=extend_schema(
        tags=["Inventário"],
        summary="Criar conciliação",
        description=(
            "Cria uma conciliação eventual para a Unidade Administrativa informada. "
            "Os itens são gerados automaticamente a partir dos bens da UA. "
            "Conciliações anuais são criadas automaticamente pelo sistema dentro "
            "do período de vigência definido nos parâmetros anuais."
        ),
        responses={
            201: OpenApiResponse(description="Conciliação criada com sucesso."),
            400: OpenApiResponse(description="Dados inválidos."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão."),
        },
    ),
)
class ConciliacaoUAViewSet(
    AuditHistoryConciliacaoMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [ConciliacaoUAPermission]
    audit_model = ConciliacaoUA
    historico_grupo_serializer_class = ConciliacaoHistoricoGrupoSerializer

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ConciliacaoUAFilter
    search_fields = [
        "numero_conciliacao",
        "unidade_administrativa__nome",
        "unidade_administrativa__codigo",
        "unidade_administrativa__sigla",
    ]
    ordering_fields = [
        "id",
        "criado_em",
        "periodo_final",
        "status",
        "tipo",
        "unidade_administrativa__codigo",
        "unidade_administrativa__sigla",
        "unidade_administrativa__nome",
    ]
    ordering = ["-criado_em", "unidade_administrativa__sigla"]

    def get_serializer_class(self):
        if self.action == "create":
            return ConciliacaoUACreateSerializer
        if self.action == "retrieve":
            return ConciliacaoUADetailSerializer
        return ConciliacaoUAListSerializer

    def get_queryset(self):
        qs = ConciliacaoUA.objects.select_related(
            "unidade_administrativa",
            "unidade_administrativa__unidade_orcamentaria",
            "criado_por",
            "fechado_por",
        )
        return filtrar_queryset_por_escopo(
            usuario=self.request.user,
            queryset=qs,
            campo_ua="unidade_administrativa",
        )

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        ano = self.request.query_params.get("ano_vigencia")
        if ano:
            queryset = _filtrar_ano_vigencia(queryset, ano)
        return queryset

    def list(self, request, *args, **kwargs):
        try:
            processar_conciliacao_anual_automatica(request.user)
        except Exception:
            pass
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            with audit_as(request.user):
                conciliacao = serializer.save()
            self._registrar_historico(
                conciliacao,
                campo="acao",
                valor_antigo="",
                valor_novo="criado",
                usuario=request.user,
                justificativa="Conciliação criada via API",
            )
            criar_itens_conciliacao(conciliacao)

        detail_serializer = ConciliacaoUADetailSerializer(
            conciliacao, context={"request": request}
        )
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        conciliacao = self.get_object()
        if conciliacao.esta_aberto:
            remover_itens_baixados_invalidos(conciliacao)
        serializer = self.get_serializer(conciliacao)
        return Response(serializer.data)

    @extend_schema(
        tags=["Inventário"],
        summary="Histórico da conciliação",
        description="Retorna o histórico de alterações da conciliação informada.",
        parameters=[CONCILIACAO_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(
                response=ConciliacaoHistoricoGrupoSerializer(many=True),
                description="Histórico retornado com sucesso.",
            ),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão."),
            404: OpenApiResponse(description="Conciliação não encontrada."),
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="historico",
        filter_backends=[],
        pagination_class=None,
    )
    def historico(self, request, pk=None):
        return self._build_historico_response(self.get_object())

    @extend_schema(
        tags=["Inventário"],
        summary="Exportar conciliação",
        description="Exporta a conciliação em PDF no padrão do relatório de campo.",
        parameters=[
            CONCILIACAO_ID_PATH_PARAM,
            OpenApiParameter(
                name="formato",
                required=False,
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                enum=["pdf"],
                description="Formato de exportação (padrão: pdf).",
            ),
        ],
        responses={
            200: OpenApiResponse(description="Arquivo PDF gerado com sucesso."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão."),
            404: OpenApiResponse(description="Conciliação não encontrada."),
        },
    )
    @action(detail=True, methods=["get"], url_path="exportar")
    def exportar(self, request, pk=None):
        serializer = ConciliacaoExportQuerySerializer(
            data=request.query_params or {"formato": "pdf"}
        )
        serializer.is_valid(raise_exception=True)

        conciliacao = self.get_object()
        pdf_buffer = gerar_pdf_conciliacao(
            conciliacao, usuario_gerador=request.user
        )

        numero = conciliacao.numero_conciliacao or str(conciliacao.pk)
        ua_codigo = (
            conciliacao.unidade_administrativa.codigo
            if conciliacao.unidade_administrativa
            else ""
        )
        ano = (
            conciliacao.periodo_final.year if conciliacao.periodo_final else ""
        )
        partes = ["CONCILIACAO", numero]
        if ano:
            partes.append(str(ano))
        if ua_codigo:
            partes.append(f"UA{ua_codigo}")
        filename = "_".join(partes) + ".pdf"

        try:
            pdf_buffer.seek(0)
        except Exception:
            pass

        response = HttpResponse(pdf_buffer, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @extend_schema(
        tags=["Inventário"],
        summary="Finalizar conciliação",
        description=(
            "Finaliza a conciliação em aberto. Aplica as mesmas regras do admin: "
            "bloqueia se já está fechada e dispara a confirmação automática de "
            "baixas físicas pendentes."
        ),
        parameters=[CONCILIACAO_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(description="Conciliação finalizada com sucesso."),
            400: OpenApiResponse(description="Conciliação já finalizada ou inválida."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão."),
            404: OpenApiResponse(description="Conciliação não encontrada."),
        },
    )
    @action(detail=True, methods=["post"], url_path="finalizar")
    def finalizar(self, request, pk=None):
        conciliacao = self.get_object()

        if not conciliacao.esta_aberto:
            raise DRFValidationError(
                {"detail": "Conciliação já está finalizada."}
            )

        with transaction.atomic():
            with audit_as(request.user):
                finalizar_conciliacao(conciliacao, request.user)
            self._registrar_historico(
                conciliacao,
                campo="status",
                valor_antigo=constants.CONCILIACAO_EM_ABERTO,
                valor_novo=conciliacao.get_status_display(),
                usuario=request.user,
                justificativa="Conciliação finalizada via API",
            )
            self._registrar_historico(
                conciliacao,
                campo="fechado_por",
                valor_antigo="",
                valor_novo=str(request.user),
                usuario=request.user,
                justificativa="Conciliação finalizada via API",
            )

        conciliacao.refresh_from_db()
        detail_serializer = ConciliacaoUADetailSerializer(
            conciliacao, context={"request": request}
        )
        return Response(detail_serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(
        tags=["Inventário"],
        summary="Listar itens de conciliação",
        description=(
            "Lista paginada dos itens de uma conciliação específica, com busca, "
            "filtros e ordenação. O escopo é automaticamente restrito à "
            "Unidade Administrativa do usuário ou à Unidade Orçamentária do gestor."
        ),
        parameters=[CONCILIACAO_NESTED_ID_PATH_PARAM, *ITEM_LIST_QUERY_PARAMETERS],
        responses={
            200: OpenApiResponse(description="Lista retornada com sucesso."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão."),
            404: OpenApiResponse(description="Conciliação não encontrada."),
        },
    ),
    retrieve=extend_schema(
        tags=["Inventário"],
        summary="Detalhar item de conciliação",
        parameters=[CONCILIACAO_NESTED_ID_PATH_PARAM, ITEM_CONCILIACAO_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(description="Detalhe retornado com sucesso."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão."),
            404: OpenApiResponse(description="Item não encontrado."),
        },
    ),
)
class ItemConciliacaoViewSet(
    AuditHistoryConciliacaoMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [ItemConciliacaoPermission]
    audit_model = ItemConciliacao
    historico_grupo_serializer_class = ConciliacaoHistoricoGrupoSerializer
    lookup_url_kwarg = "item_id"

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = ItemConciliacaoFilter
    search_fields = [
        "bem__numero_patrimonial",
        "bem__nome",
    ]
    ordering_fields = [
        "id",
        "atualizado_em",
        "situacao",
        "bem__numero_patrimonial",
        "bem__nome",
    ]
    ordering = ["bem__numero_patrimonial"]

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ItemConciliacaoDetailSerializer
        return ItemConciliacaoListSerializer

    def get_queryset(self):
        qs = ItemConciliacao.objects.select_related(
            "bem",
            "bem__unidade_administrativa",
            "conciliacao",
            "conciliacao__unidade_administrativa",
            "conciliacao__unidade_administrativa__unidade_orcamentaria",
            "atualizado_por",
        ).prefetch_related("ocorrencias__registrado_por")
        qs = filtrar_queryset_por_escopo(
            usuario=self.request.user,
            queryset=qs,
            campo_ua="conciliacao__unidade_administrativa",
        )

        conciliacao_pk = self.kwargs.get("conciliacao_pk")
        if conciliacao_pk:
            qs = qs.filter(conciliacao_id=conciliacao_pk)
        return qs

    def _get_conciliacao(self):
        conciliacao_pk = self.kwargs.get("conciliacao_pk")
        if not conciliacao_pk:
            return None
        qs = filtrar_queryset_por_escopo(
            usuario=self.request.user,
            queryset=ConciliacaoUA.objects.all(),
            campo_ua="unidade_administrativa",
        )
        conciliacao = qs.filter(pk=conciliacao_pk).first()
        if not conciliacao:
            raise NotFound("Conciliação não encontrada.")
        return conciliacao

    def list(self, request, *args, **kwargs):
        self._get_conciliacao()
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        self._get_conciliacao()
        return super().retrieve(request, *args, **kwargs)

    def get_object(self):
        item = super().get_object()
        conciliacao_pk = self.kwargs.get("conciliacao_pk")
        if conciliacao_pk and item.conciliacao_id != int(conciliacao_pk):
            raise NotFound("Item não pertence à conciliação informada.")
        return item

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        tem_ocorrencia = self.request.query_params.get("tem_ocorrencia")
        if tem_ocorrencia in ("true", "True", "1"):
            queryset = queryset.filter(ocorrencias__isnull=False).distinct()
        elif tem_ocorrencia in ("false", "False", "0"):
            queryset = queryset.filter(ocorrencias__isnull=True)
        return queryset

    @extend_schema(
        tags=["Inventário"],
        summary="Situações disponíveis para ocorrência",
        description=(
            "Retorna as situações que podem ser usadas ao registrar/editar a "
            "ocorrência do item, respeitando as regras do admin (ex.: bloqueia "
            "Baixa Física e limites de resolução)."
        ),
        parameters=[CONCILIACAO_NESTED_ID_PATH_PARAM, ITEM_CONCILIACAO_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(description="Lista de situações disponíveis."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão."),
            404: OpenApiResponse(description="Item não encontrado."),
        },
    )
    def situacoes_disponiveis(self, request, conciliacao_pk=None, item_id=None):
        self._get_conciliacao()
        item = self.get_object()
        situacoes = self._get_situacoes_disponiveis_para_item(item)
        return Response(
            [{"value": v, "label": l} for v, l in situacoes]
        )

    def _get_situacoes_disponiveis_para_item(self, item):
        situacoes = list(constants.SITUACOES_ITEM_CONCILIACAO)
        situacoes = [s for s in situacoes if s[0] != constants.BAIXA_FISICA]

        if not item.pode_resolver_situacao:
            situacoes = [
                s for s in situacoes if s[0] != constants.ENCONTRADO_SEM_DIVERGENCIA
            ]

        if not item.pode_marcar_como_encontrado:
            situacoes = [s for s in situacoes if s[0] != constants.ENCONTRADO]

        return situacoes

    @extend_schema(
        tags=["Inventário"],
        summary="Registrar ocorrência do item",
        description=(
            "Registra ou atualiza a ocorrência do item de conciliação. "
            "Replica as regras do admin: bloqueia se a conciliação está fechada, "
            "se o item está em Baixa Física e exige divergência quando a "
            "situação for 'Divergente'."
        ),
        parameters=[CONCILIACAO_NESTED_ID_PATH_PARAM, ITEM_CONCILIACAO_ID_PATH_PARAM],
        request=RegistrarOcorrenciaSerializer,
        responses={
            200: OpenApiResponse(description="Ocorrência registrada com sucesso."),
            400: OpenApiResponse(description="Dados inválidos."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão."),
            404: OpenApiResponse(description="Item não encontrado."),
        },
    )
    def registrar_ocorrencia(self, request, conciliacao_pk=None, item_id=None):
        self._get_conciliacao()
        item = self.get_object()
        self._validar_item_para_ocorrencia(item)

        serializer = RegistrarOcorrenciaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        situacao_anterior = item.get_situacao_display()

        try:
            registrar_ocorrencia(
                item=item,
                situacao=serializer.validated_data["situacao"],
                observacao=serializer.validated_data.get("observacao", ""),
                divergencia=serializer.validated_data.get("divergencia", ""),
                usuario=request.user,
            )
        except DjangoValidationError as exc:
            self._raise_drf_validation_error(exc)

        self._registrar_historico(
            item,
            campo="situacao",
            valor_antigo=situacao_anterior,
            valor_novo=dict(constants.SITUACOES_ITEM_CONCILIACAO).get(
                serializer.validated_data["situacao"],
                serializer.validated_data["situacao"],
            ),
            usuario=request.user,
            justificativa="Ocorrência registrada via API",
        )

        item.refresh_from_db()
        detail_serializer = ItemConciliacaoDetailSerializer(
            item, context={"request": request}
        )
        return Response(detail_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Inventário"],
        summary="Excluir ocorrência do item",
        description=(
            "Exclui a última ocorrência do item e restaura a situação anterior "
            "conforme regras do admin. Bloqueia se a conciliação está fechada "
            "ou se o item não tem ocorrência."
        ),
        parameters=[CONCILIACAO_NESTED_ID_PATH_PARAM, ITEM_CONCILIACAO_ID_PATH_PARAM],
        request=None,
        responses={
            200: OpenApiResponse(description="Ocorrência excluída com sucesso."),
            400: OpenApiResponse(description="Item sem ocorrência ou conciliação fechada."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão."),
            404: OpenApiResponse(description="Item não encontrado."),
        },
    )
    def excluir_ocorrencia(self, request, conciliacao_pk=None, item_id=None):
        self._get_conciliacao()
        item = self.get_object()

        if not item.conciliacao.esta_aberto:
            raise DRFValidationError(
                {"detail": "Conciliação fechada não permite edições."}
            )

        situacao_anterior = item.get_situacao_display()

        try:
            excluir_ocorrencia(item=item, usuario=request.user)
        except DjangoValidationError as exc:
            self._raise_drf_validation_error(exc)

        self._registrar_historico(
            item,
            campo="situacao",
            valor_antigo=situacao_anterior,
            valor_novo=item.get_situacao_display(),
            usuario=request.user,
            justificativa="Ocorrência excluída via API",
        )

        item.refresh_from_db()
        detail_serializer = ItemConciliacaoDetailSerializer(
            item, context={"request": request}
        )
        return Response(detail_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Inventário"],
        summary="Histórico do item de conciliação",
        description="Retorna o histórico de alterações do item de conciliação.",
        parameters=[CONCILIACAO_NESTED_ID_PATH_PARAM, ITEM_CONCILIACAO_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(
                response=ConciliacaoHistoricoGrupoSerializer(many=True),
                description="Histórico retornado com sucesso.",
            ),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão."),
            404: OpenApiResponse(description="Item não encontrado."),
        },
    )
    def historico(self, request, conciliacao_pk=None, item_id=None):
        self._get_conciliacao()
        return self._build_historico_response(self.get_object())

    def _validar_item_para_ocorrencia(self, item):
        if not item.conciliacao.esta_aberto:
            raise DRFValidationError(
                {"detail": "Conciliação fechada não permite edições."}
            )
        if not item.permite_registrar_ocorrencia:
            raise DRFValidationError(
                {
                    "detail": (
                        "Bem com status 'Baixa Física' não pode ter ocorrência "
                        "registrada. Este status é definitivo."
                    )
                }
            )

    def _raise_drf_validation_error(self, exc):
        if hasattr(exc, "message_dict"):
            errors = dict(exc.message_dict)
            if "__all__" in errors:
                errors["non_field_errors"] = errors.pop("__all__")
            raise DRFValidationError(errors)
        if hasattr(exc, "messages"):
            raise DRFValidationError({"non_field_errors": exc.messages})
        raise DRFValidationError({"non_field_errors": [str(exc)]})
