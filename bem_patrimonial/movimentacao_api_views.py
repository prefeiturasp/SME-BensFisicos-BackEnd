from collections import defaultdict
from datetime import timedelta
import logging

from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone

import django_filters
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from bem_patrimonial import constants
from bem_patrimonial.cimbpm import gerar_pdf_cimbpm
from bem_patrimonial.emails import (
    envia_email_solicitacao_movimentacao_aceita,
    envia_email_solicitacao_movimentacao_cancelada,
    envia_email_solicitacao_movimentacao_rejeitada,
)
from bem_patrimonial.models import MovimentacaoBemPatrimonial
from bem_patrimonial.serializers.movimentacao_serializers import (
    MovimentacaoBemPatrimonialCreateSerializer,
    MovimentacaoBemPatrimonialDetailSerializer,
    MovimentacaoBemPatrimonialListSerializer,
    MovimentacaoBemPatrimonialUpdateSerializer,
    MovimentacaoHistoricoGrupoSerializer,
)
from dados_comuns.context import audit_as
from dados_comuns.escopo import filtrar_queryset_movimentacao_por_escopo
from dados_comuns.models import HistoricoGeral
from dados_comuns.permissions import MovimentacaoBemPatrimonialPermission

logger = logging.getLogger(__name__)

MOVIMENTACAO_ID_PATH_PARAM = OpenApiParameter(
    name="id",
    required=True,
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    description="Identificador numérico único da movimentação.",
)

MOVIMENTACAO_LIST_QUERY_PARAMETERS = [
    OpenApiParameter(
        name="search",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description=(
            "Busca em: numero_cimbpm, código/nome/sigla da UA de origem e destino, "
            "código/nome da UO de origem e destino, número patrimonial, nome, descrição, "
            "marca, modelo, localização e número do processo do bem."
        ),
    ),
    OpenApiParameter(
        name="ordering",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description=(
            "Ordenação por: id, criado_em, atualizado_em, status, numero_cimbpm, "
            "unidade_administrativa_origem__sigla e unidade_administrativa_destino__sigla. "
            "Use '-' para descendente."
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
        name="status",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description=(
            "Filtra por status da movimentação. Aceita um valor ou vários separados "
            "por vírgula."
        ),
    ),
    OpenApiParameter(
        name="unidade_administrativa_origem",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="Filtra pela unidade administrativa de origem.",
    ),
    OpenApiParameter(
        name="unidade_administrativa_destino",
        type=OpenApiTypes.INT,
        location=OpenApiParameter.QUERY,
        description="Filtra pela unidade administrativa de destino.",
    ),
    OpenApiParameter(
        name="numero_cimbpm",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="Filtra pelo número CIMBPM.",
    ),
    OpenApiParameter(
        name="numero_patrimonial_inicial",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="Filtra movimentações com bens cujo número patrimonial seja maior ou igual ao valor informado.",
    ),
    OpenApiParameter(
        name="numero_patrimonial_final",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description="Filtra movimentações com bens cujo número patrimonial seja menor ou igual ao valor informado.",
    ),
    OpenApiParameter(
        name="atrasada",
        type=OpenApiTypes.STR,
        location=OpenApiParameter.QUERY,
        description=(
            "Filtra movimentações atrasadas. Aceita 1, true ou True para mostrar "
            "apenas movimentações enviadas há 7 dias ou mais."
        ),
    ),
]

JUSTIFICATIVA_MOVIMENTACAO_CRIADA_VIA_API = "Movimentação criada via API"


class MovimentacaoBemPatrimonialFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(method="filter_status")
    atrasada = django_filters.CharFilter(method="filter_atrasada")
    numero_patrimonial_inicial = django_filters.CharFilter(
        method="filter_numero_patrimonial_inicial"
    )
    numero_patrimonial_final = django_filters.CharFilter(
        method="filter_numero_patrimonial_final"
    )

    class Meta:
        model = MovimentacaoBemPatrimonial
        fields = [
            "status",
            "unidade_administrativa_origem",
            "unidade_administrativa_destino",
            "numero_cimbpm",
        ]

    def filter_status(self, queryset, name, value):
        if not value:
            return queryset
        valores = [item.strip() for item in value.split(",") if item.strip()]
        if len(valores) == 1:
            return queryset.filter(status=valores[0])
        return queryset.filter(status__in=valores)

    def filter_atrasada(self, queryset, name, value):
        if value not in ("1", "true", "True"):
            return queryset
        limite = timezone.now() - timedelta(days=7)
        return queryset.filter(status=constants.ENVIADA, criado_em__lte=limite)

    def filter_numero_patrimonial_inicial(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(itens__bem__numero_patrimonial__gte=value)

    def filter_numero_patrimonial_final(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(itens__bem__numero_patrimonial__lte=value)


@extend_schema_view(
    partial_update=extend_schema(
        tags=["Movimentações"],
        summary="Atualizar parcialmente movimentação",
        description="Nesta versão da API, apenas observação pode ser alterada.",
        parameters=[MOVIMENTACAO_ID_PATH_PARAM],
        responses={200: MovimentacaoBemPatrimonialDetailSerializer},
    ),
)
class MovimentacaoBemPatrimonialViewSet(viewsets.ModelViewSet):
    permission_classes = [MovimentacaoBemPatrimonialPermission]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = MovimentacaoBemPatrimonialFilter
    search_fields = (
        "numero_cimbpm",
        "unidade_administrativa_origem__codigo",
        "unidade_administrativa_origem__nome",
        "unidade_administrativa_origem__sigla",
        "unidade_administrativa_destino__codigo",
        "unidade_administrativa_destino__nome",
        "unidade_administrativa_destino__sigla",
        "unidade_administrativa_origem__unidade_orcamentaria__codigo",
        "unidade_administrativa_origem__unidade_orcamentaria__nome",
        "unidade_administrativa_destino__unidade_orcamentaria__codigo",
        "unidade_administrativa_destino__unidade_orcamentaria__nome",
        "itens__bem__numero_patrimonial",
        "itens__bem__nome",
        "itens__bem__descricao",
        "itens__bem__marca",
        "itens__bem__modelo",
        "itens__bem__localizacao",
        "itens__bem__numero_processo",
    )
    ordering_fields = [
        "id",
        "criado_em",
        "atualizado_em",
        "status",
        "numero_cimbpm",
        "unidade_administrativa_origem__sigla",
        "unidade_administrativa_destino__sigla",
    ]
    ordering = ["-criado_em"]

    def get_serializer_class(self):
        if self.action == "list":
            return MovimentacaoBemPatrimonialListSerializer
        if self.action in ("update", "partial_update"):
            return MovimentacaoBemPatrimonialUpdateSerializer
        if self.action == "create":
            return MovimentacaoBemPatrimonialCreateSerializer
        return MovimentacaoBemPatrimonialDetailSerializer

    def get_queryset(self):
        qs = (
            MovimentacaoBemPatrimonial.objects.select_related(
                "bem_patrimonial",
                "unidade_administrativa_origem",
                "unidade_administrativa_origem__unidade_orcamentaria",
                "unidade_administrativa_destino",
                "unidade_administrativa_destino__unidade_orcamentaria",
                "solicitado_por",
                "aprovado_por",
                "rejeitado_por",
                "cancelado_por",
            )
            .prefetch_related("itens__bem", "itens__bem__unidade_administrativa")
        )
        return filtrar_queryset_movimentacao_por_escopo(self.request.user, qs).distinct()

    def _content_type(self):
        return ContentType.objects.get_for_model(MovimentacaoBemPatrimonial)

    def _registrar_historico(self, mov, campo, valor_antigo, valor_novo, usuario, justificativa=""):
        HistoricoGeral.objects.create(
            content_type=self._content_type(),
            object_id=str(mov.pk),
            campo=campo,
            valor_antigo=str(valor_antigo) if valor_antigo is not None else "",
            valor_novo=str(valor_novo) if valor_novo is not None else "",
            alterado_por=usuario,
            justificativa=justificativa,
        )

    def _registrar_historico_bulk(self, mov, registros, usuario):
        HistoricoGeral.objects.bulk_create(
            [
                HistoricoGeral(
                    content_type=self._content_type(),
                    object_id=str(mov.pk),
                    campo=item["campo"],
                    valor_antigo=str(item.get("valor_antigo") or ""),
                    valor_novo=str(item.get("valor_novo") or ""),
                    alterado_por=usuario,
                    justificativa=item.get("justificativa", ""),
                )
                for item in registros
            ]
        )

    def _historico_agrupado(self, mov):
        registros = (
            HistoricoGeral.objects.filter(
                content_type=self._content_type(),
                object_id=str(mov.pk),
            )
            .select_related("alterado_por")
            .order_by("-alterado_em")
        )

        agrupado = defaultdict(list)
        for item in registros:
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
                            "campo": item.campo,
                            "valor_antigo": item.valor_antigo,
                            "valor_novo": item.valor_novo,
                            "justificativa": item.justificativa,
                        }
                        for item in itens
                    ],
                }
            )

        resposta = sorted(resposta, key=lambda row: row["alterado_em"], reverse=True)
        serializer = MovimentacaoHistoricoGrupoSerializer(resposta, many=True)
        return serializer.data

    def _movimentacao_entre_uos_diferentes(self, mov):
        origem_uo_id = getattr(
            mov.unidade_administrativa_origem, "unidade_orcamentaria_id", None
        )
        destino_uo_id = getattr(
            mov.unidade_administrativa_destino, "unidade_orcamentaria_id", None
        )
        return bool(origem_uo_id and destino_uo_id and origem_uo_id != destino_uo_id)

    def _obter_uo_id_do_usuario(self, usuario):
        uo_id = getattr(usuario, "unidade_orcamentaria_id", None)
        if uo_id:
            return uo_id
        unidade_administrativa = getattr(usuario, "unidade_administrativa", None)
        return getattr(unidade_administrativa, "unidade_orcamentaria_id", None)

    def _usuario_e_gestor_da_uo(self, usuario, uo_id):
        return bool(
            getattr(usuario, "is_gestor_patrimonio", False)
            and self._obter_uo_id_do_usuario(usuario) == uo_id
        )

    def _validar_status_movimentacao_para_acao(self, mov, acao):
        if getattr(mov, "status", None) != constants.ENVIADA:
            raise ValidationError(
                f"Movimentação #{mov.pk}: apenas movimentações enviadas podem ser {acao}."
            )
        if mov.aceita:
            raise ValidationError(f"Movimentação #{mov.pk} já foi aprovada anteriormente.")
        if mov.rejeitada:
            raise ValidationError(f"Movimentação #{mov.pk} já foi rejeitada anteriormente.")
        if mov.cancelada:
            raise ValidationError(f"Movimentação #{mov.pk} foi cancelada e não pode ser processada.")

    def _validar_unidades_ativas_para_acao(self, mov):
        if not mov.unidade_administrativa_origem.is_ativa:
            raise ValidationError(
                {
                    "unidade_administrativa_origem": (
                        f"A unidade de origem '{mov.unidade_administrativa_origem.nome}' está inativa."
                    )
                }
            )
        if not mov.unidade_administrativa_destino.is_ativa:
            raise ValidationError(
                {
                    "unidade_administrativa_destino": (
                        f"A unidade de destino '{mov.unidade_administrativa_destino.nome}' está inativa."
                    )
                }
            )

    def _validar_acao_por_operador(self, mov, user, acao):
        if mov.unidade_administrativa_destino_id != user.unidade_administrativa_id:
            raise PermissionDenied(
                f"Movimentação #{mov.pk}: apenas operadores da unidade de destino podem {acao} esta movimentação."
            )
        if mov.solicitado_por_id == user.pk:
            raise ValidationError(
                f"Movimentação #{mov.pk}: você não pode {acao} sua própria solicitação."
            )

    def _validar_acao_em_uos_diferentes(self, mov, user, acao):
        if mov.solicitado_por_id == user.pk:
            raise ValidationError(
                f"Movimentação #{mov.pk}: você não pode {acao} sua própria solicitação em movimentações entre UOs."
            )

        if getattr(user, "is_operador_inventario", False) and not getattr(
            user, "is_gestor_patrimonio", False
        ):
            self._validar_acao_por_operador(mov, user, acao)
            return

        if getattr(user, "is_gestor_patrimonio", False):
            destino_uo_id = mov.unidade_administrativa_destino.unidade_orcamentaria_id
            if not self._usuario_e_gestor_da_uo(user, destino_uo_id):
                raise PermissionDenied(
                    f"Movimentação #{mov.pk}: apenas gestores da UO de destino podem {acao} esta movimentação entre UOs."
                )

    def _validar_acao_na_mesma_uo(self, mov, user, acao):
        if getattr(user, "is_operador_inventario", False) and not getattr(
            user, "is_gestor_patrimonio", False
        ):
            self._validar_acao_por_operador(mov, user, acao)

    def _validar_acao(self, mov, user, acao):
        self._validar_status_movimentacao_para_acao(mov, acao)
        self._validar_tem_itens_para_acao(mov)
        self._validar_unidades_ativas_para_acao(mov)

        if self._movimentacao_entre_uos_diferentes(mov):
            self._validar_acao_em_uos_diferentes(mov, user, acao)
            return

        self._validar_acao_na_mesma_uo(mov, user, acao)

    def _validar_tem_itens_para_acao(self, mov):
        if not mov.itens.exists():
            raise ValidationError(
                {"itens": f"Movimentação #{mov.pk} não possui bens associados."}
            )

    def _validar_cancelamento_por_operador(self, mov, user):
        if mov.solicitado_por_id != user.pk:
            raise ValidationError(
                f"Movimentação #{mov.pk}: você só pode cancelar movimentações criadas por você."
            )

    def _validar_cancelamento_por_gestor(self, mov, user):
        usuario_uo_id = self._obter_uo_id_do_usuario(user)
        origem_uo_id = mov.unidade_administrativa_origem.unidade_orcamentaria_id
        destino_uo_id = mov.unidade_administrativa_destino.unidade_orcamentaria_id
        if usuario_uo_id not in (origem_uo_id, destino_uo_id):
            raise PermissionDenied(
                f"Movimentação #{mov.pk}: apenas gestores da UO de origem ou destino podem cancelar esta movimentação entre UOs."
            )

    def _validar_cancelamento_em_uos_diferentes(self, mov, user):
        if getattr(user, "is_operador_inventario", False) and not getattr(
            user, "is_gestor_patrimonio", False
        ):
            self._validar_cancelamento_por_operador(mov, user)
            return

        if getattr(user, "is_gestor_patrimonio", False):
            self._validar_cancelamento_por_gestor(mov, user)

    def _validar_cancelamento_na_mesma_uo(self, mov, user):
        if getattr(user, "is_operador_inventario", False) and not getattr(
            user, "is_gestor_patrimonio", False
        ):
            self._validar_cancelamento_por_operador(mov, user)

    def _validar_cancelamento(self, mov, user):
        if getattr(mov, "status", None) != constants.ENVIADA:
            raise ValidationError(
                f"Movimentação #{mov.pk}: apenas movimentações enviadas podem ser canceladas."
            )
        if mov.aceita:
            raise ValidationError(
                f"Movimentação #{mov.pk} já foi aprovada e não pode ser cancelada."
            )
        if mov.rejeitada:
            raise ValidationError(
                f"Movimentação #{mov.pk} já foi rejeitada e não pode ser cancelada."
            )
        if mov.cancelada:
            raise ValidationError(
                f"Movimentação #{mov.pk} já foi cancelada anteriormente."
            )

        if self._movimentacao_entre_uos_diferentes(mov):
            self._validar_cancelamento_em_uos_diferentes(mov, user)
            return

        self._validar_cancelamento_na_mesma_uo(mov, user)

    def _registrar_evento(self, mov, usuario, acao, status_anterior):
        campo_usuario = {
            constants.ACEITA: "aprovado_por",
            constants.REJEITADA: "rejeitado_por",
            constants.CANCELADA: "cancelado_por",
        }[mov.status]
        self._registrar_historico(
            mov,
            campo="status",
            valor_antigo=status_anterior,
            valor_novo=mov.get_status_display(),
            usuario=usuario,
            justificativa=f"Movimentação {acao} via API",
        )
        self._registrar_historico(
            mov,
            campo=campo_usuario,
            valor_antigo="",
            valor_novo=str(usuario),
            usuario=usuario,
            justificativa=f"Movimentação {acao} via API",
        )

    def _notificar_solicitante(self, envio_fn, *args):
        try:
            envio_fn(*args)
        except Exception:
            logger.exception("Falha ao enviar email de movimentação via API")

    @extend_schema(
        tags=["Movimentações"],
        summary="Listar movimentações",
        description="Lista paginada com busca, filtros e ordenação.",
        parameters=MOVIMENTACAO_LIST_QUERY_PARAMETERS,
        responses={200: MovimentacaoBemPatrimonialListSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        tags=["Movimentações"],
        summary="Detalhar movimentação",
        description="Retorna os dados completos de uma movimentação.",
        parameters=[MOVIMENTACAO_ID_PATH_PARAM],
        responses={200: MovimentacaoBemPatrimonialDetailSerializer},
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        tags=["Movimentações"],
        summary="Criar movimentação",
        description="Cria uma movimentação e bloqueia automaticamente os bens incluídos.",
        responses={201: MovimentacaoBemPatrimonialDetailSerializer},
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            with audit_as(request.user):
                movimentacao = serializer.save()
                self._registrar_historico(
                    movimentacao,
                    campo="status",
                    valor_antigo="",
                    valor_novo=movimentacao.get_status_display(),
                    usuario=request.user,
                    justificativa=JUSTIFICATIVA_MOVIMENTACAO_CRIADA_VIA_API,
                )
                self._registrar_historico(
                    movimentacao,
                    campo="unidade_administrativa_origem",
                    valor_antigo="",
                    valor_novo=str(movimentacao.unidade_administrativa_origem),
                    usuario=request.user,
                    justificativa=JUSTIFICATIVA_MOVIMENTACAO_CRIADA_VIA_API,
                )
                self._registrar_historico(
                    movimentacao,
                    campo="unidade_administrativa_destino",
                    valor_antigo="",
                    valor_novo=str(movimentacao.unidade_administrativa_destino),
                    usuario=request.user,
                    justificativa=JUSTIFICATIVA_MOVIMENTACAO_CRIADA_VIA_API,
                )
                self._registrar_historico_bulk(
                    movimentacao,
                    [
                        {
                            "campo": "itens",
                            "valor_antigo": "",
                            "valor_novo": str(item.bem),
                            "justificativa": "Bem incluído na movimentação",
                        }
                        for item in movimentacao.itens.select_related("bem")
                    ],
                    request.user,
                )

        detail = MovimentacaoBemPatrimonialDetailSerializer(
            movimentacao, context={"request": request}
        )
        return Response(detail.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["Movimentações"],
        summary="Atualizar movimentação",
        description="Nesta versão da API, apenas observação pode ser alterada.",
        parameters=[MOVIMENTACAO_ID_PATH_PARAM],
        responses={200: MovimentacaoBemPatrimonialDetailSerializer},
    )
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        observacao_anterior = instance.observacao

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            with audit_as(request.user):
                movimentacao = serializer.save()
                if (observacao_anterior or "") != (movimentacao.observacao or ""):
                    self._registrar_historico(
                        movimentacao,
                        campo="observacao",
                        valor_antigo=observacao_anterior,
                        valor_novo=movimentacao.observacao,
                        usuario=request.user,
                        justificativa="Observação atualizada via API",
                    )

        detail = MovimentacaoBemPatrimonialDetailSerializer(
            movimentacao, context={"request": request}
        )
        return Response(detail.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Movimentações"],
        summary="Atualizar parcialmente movimentação",
        description="Nesta versão da API, apenas observação pode ser alterada.",
        parameters=[MOVIMENTACAO_ID_PATH_PARAM],
        responses={200: MovimentacaoBemPatrimonialDetailSerializer},
    )
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @extend_schema(
        tags=["Movimentações"],
        summary="Aprovar movimentação",
        description="Aprova a movimentação e move os bens para a unidade de destino.",
        request=None,
        parameters=[MOVIMENTACAO_ID_PATH_PARAM],
        responses={200: MovimentacaoBemPatrimonialDetailSerializer},
    )
    @action(detail=True, methods=["post"])
    def aprovar(self, request, pk=None):
        mov = self.get_object()
        self._validar_acao(mov, request.user, "aprovar")

        with audit_as(request.user):
            with transaction.atomic():
                mov = MovimentacaoBemPatrimonial.objects.select_for_update().get(pk=mov.pk)
                status_anterior = mov.get_status_display()
                mov.aprovar_solicitacao(request.user)
                self._registrar_evento(mov, request.user, "aprovada", status_anterior)

        if mov.solicitado_por and mov.solicitado_por.email and settings.DEFAULT_FROM_EMAIL:
            emails = [mov.solicitado_por.email]
            for item in mov.itens.select_related("bem"):
                self._notificar_solicitante(
                    envia_email_solicitacao_movimentacao_aceita,
                    item.bem,
                    emails,
                )

        return Response(
            MovimentacaoBemPatrimonialDetailSerializer(mov, context={"request": request}).data
        )

    @extend_schema(
        tags=["Movimentações"],
        summary="Rejeitar movimentação",
        description="Rejeita a movimentação e restaura o status dos bens.",
        request=None,
        parameters=[MOVIMENTACAO_ID_PATH_PARAM],
        responses={200: MovimentacaoBemPatrimonialDetailSerializer},
    )
    @action(detail=True, methods=["post"])
    def rejeitar(self, request, pk=None):
        mov = self.get_object()
        self._validar_acao(mov, request.user, "rejeitar")

        with audit_as(request.user):
            with transaction.atomic():
                mov = MovimentacaoBemPatrimonial.objects.select_for_update().get(pk=mov.pk)
                status_anterior = mov.get_status_display()
                mov.rejeitar_solicitacao(request.user)
                self._registrar_evento(mov, request.user, "rejeitada", status_anterior)

        if mov.solicitado_por and mov.solicitado_por.email and settings.DEFAULT_FROM_EMAIL:
            emails = [mov.solicitado_por.email]
            for item in mov.itens.select_related("bem"):
                self._notificar_solicitante(
                    envia_email_solicitacao_movimentacao_rejeitada,
                    item.bem,
                    emails,
                )

        return Response(
            MovimentacaoBemPatrimonialDetailSerializer(mov, context={"request": request}).data
        )

    @extend_schema(
        tags=["Movimentações"],
        summary="Cancelar movimentação",
        description="Cancela a movimentação e restaura o status dos bens.",
        request=None,
        parameters=[MOVIMENTACAO_ID_PATH_PARAM],
        responses={200: MovimentacaoBemPatrimonialDetailSerializer},
    )
    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        mov = self.get_object()
        self._validar_cancelamento(mov, request.user)

        with audit_as(request.user):
            with transaction.atomic():
                mov = MovimentacaoBemPatrimonial.objects.select_for_update().get(pk=mov.pk)
                status_anterior = mov.get_status_display()
                mov.cancelar_solicitacao(request.user)
                self._registrar_evento(mov, request.user, "cancelada", status_anterior)

        if mov.solicitado_por and mov.solicitado_por.email and settings.DEFAULT_FROM_EMAIL:
            emails = [mov.solicitado_por.email]
            for item in mov.itens.select_related("bem"):
                self._notificar_solicitante(
                    envia_email_solicitacao_movimentacao_cancelada,
                    item.bem,
                    request.user,
                    emails,
                )

        return Response(
            MovimentacaoBemPatrimonialDetailSerializer(mov, context={"request": request}).data
        )

    @extend_schema(
        tags=["Movimentações"],
        summary="Histórico da movimentação",
        description="Retorna o histórico agrupado da movimentação.",
        request=None,
        parameters=[MOVIMENTACAO_ID_PATH_PARAM, *MOVIMENTACAO_LIST_QUERY_PARAMETERS],
        responses={200: MovimentacaoHistoricoGrupoSerializer(many=True)},
    )
    @action(detail=True, methods=["get"], url_path="historico")
    def historico(self, request, pk=None):
        mov = self.get_object()
        return Response(self._historico_agrupado(mov))

    @extend_schema(
        tags=["Movimentações"],
        summary="Baixar documento CIMBPM",
        description="Retorna o PDF CIMBPM da movimentação.",
        request=None,
        parameters=[MOVIMENTACAO_ID_PATH_PARAM],
        responses={200: OpenApiResponse(description="Arquivo PDF CIMBPM")},
    )
    @action(detail=True, methods=["get"], url_path="documento-cimbpm")
    def documento_cimbpm(self, request, pk=None):
        mov = self.get_object()
        if not mov.numero_cimbpm:
            raise NotFound("Número CIMBPM não gerado para esta movimentação.")

        pdf_buffer = gerar_pdf_cimbpm(
            mov,
            usuario_gerador=request.user,
            data_geracao=timezone.now(),
        )
        filename = f"CIMBPM_{mov.numero_cimbpm.replace('.', '_')}.pdf"
        return FileResponse(
            pdf_buffer,
            as_attachment=True,
            filename=filename,
            content_type="application/pdf",
        )
