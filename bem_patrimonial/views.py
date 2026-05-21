from collections import defaultdict

from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET
from django.db.models import OuterRef, Subquery
from django.db import models, transaction

from rest_framework import viewsets, status as http_status
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError as DRFValidationError

from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.contenttypes.models import ContentType
from django.db.models.functions import Cast

from bem_patrimonial import constants
from bem_patrimonial.serializers.bem_patrimonial_serializers import (
    BemPatrimonialListSerializer,
    BemPatrimonialDetailSerializer,
    BemPatrimonialMultiCreateSerializer,
)
from bem_patrimonial.serializers.historico_serializers import HistoricoGrupoSerializer

from dados_comuns.permissions import BemPatrimonialPermission

from bem_patrimonial.models import (
    BaixaFisicaBensItem,
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
    TransferenciaBemPatrimonial,
)
from dados_comuns.models import HistoricoGeral
from dados_comuns.context import audit_as
from dados_comuns.escopo import (
    filtrar_queryset_bem_por_escopo_com_transferencia,
    filtrar_queryset_por_escopo,
    filtrar_queryset_transferencia_por_escopo,
    validar_bem_no_escopo_com_transferencia,
)


@login_required
@require_GET
def download_documento_cimbpm(request, pk):
    movimentacao = get_object_or_404(MovimentacaoBemPatrimonial, pk=pk)

    if request.user.is_operador_inventario and not request.user.is_gestor_patrimonio:
        user_ua = request.user.unidade_administrativa

        if (
            movimentacao.unidade_administrativa_origem != user_ua
            and movimentacao.unidade_administrativa_destino != user_ua
        ):
            raise PermissionDenied(
                "Você não tem permissão para acessar este documento. "
                "Operadores só podem baixar documentos de movimentações "
                "relacionadas à sua Unidade Administrativa."
            )

    if not movimentacao.numero_cimbpm:
        raise Http404("Erro: Número CIMBPM não foi gerado para esta movimentação")

    from bem_patrimonial.cimbpm import gerar_pdf_cimbpm

    data_aceite = None
    if movimentacao.aceita and movimentacao.aprovado_por:
        data_aceite = movimentacao.atualizado_em

    try:
        pdf_buffer = gerar_pdf_cimbpm(
            movimentacao,
            data_aceite=data_aceite,
            usuario_gerador=request.user,
            data_geracao=timezone.now(),
        )
    except Exception as e:
        raise Http404(f"Erro ao gerar documento: {str(e)}")

    filename = f"CIMBPM_{movimentacao.numero_cimbpm.replace('.', '_')}.pdf"

    return FileResponse(
        pdf_buffer,
        as_attachment=True,
        filename=filename,
        content_type="application/pdf",
    )


@login_required
@require_GET
def download_documento_ntbpm(request, pk):
    if not request.user.is_gestor_patrimonio:
        raise PermissionDenied(
            "Você não tem permissão para acessar este documento. "
            "Apenas Gestor de Patrimônio pode baixar documentos de transferência."
        )

    transferencia = get_object_or_404(
        filtrar_queryset_transferencia_por_escopo(
            request.user,
            TransferenciaBemPatrimonial.objects.all(),
        ),
        pk=pk,
    )

    if not transferencia.numero_ntbpm:
        raise Http404("Erro: Número NTBPM não foi gerado para esta transferência")

    from bem_patrimonial.ntbpm import gerar_pdf_ntbpm

    try:
        pdf_buffer = gerar_pdf_ntbpm(
            transferencia,
            usuario_gerador=request.user,
            data_geracao=timezone.now(),
        )
    except Exception as e:
        raise Http404(f"Erro ao gerar documento: {str(e)}")

    filename = f"NTBPM_{transferencia.numero_ntbpm.replace('.', '_')}.pdf"

    return FileResponse(
        pdf_buffer,
        as_attachment=True,
        filename=filename,
        content_type="application/pdf",
    )


class BemPatrimonialViewSet(viewsets.ModelViewSet):
    permission_classes = [BemPatrimonialPermission]
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    filterset_fields = [
        "status",
        "sem_numeracao",
        "numero_formato_antigo",
        "bloqueado_conciliacao",
        "unidade_administrativa",
    ]

    search_fields = [
        "numero_patrimonial",
        "nome",
        "descricao",
        "marca",
        "modelo",
        "localizacao",
        "numero_processo",
        "unidade_administrativa__codigo",
        "unidade_administrativa__nome",
    ]

    ordering_fields = [
        "criado_em",
        "atualizado_em",
        "nome",
        "numero_patrimonial",
        "unidade_administrativa__nome",
        "status",
    ]
    ordering = ["-criado_em"]

    def get_serializer_class(self):
        if self.action == "list":
            return BemPatrimonialListSerializer
        return BemPatrimonialDetailSerializer

    def get_queryset(self):
        busca_geral_uos = self.request.query_params.get("busca_geral_uos")
        qs = BemPatrimonial.objects.select_related(
            "unidade_administrativa",
            "unidade_administrativa__unidade_orcamentaria",
            "criado_por",
        )
        action = getattr(self, "action", None)
        pode_visualizar_fora_escopo = action in {"retrieve", "historico"} and (
            getattr(self.request.user, "is_gestor_patrimonio", False)
            or getattr(self.request.user, "is_operador_inventario", False)
            or getattr(self.request.user, "is_superuser", False)
        )

        if pode_visualizar_fora_escopo:
            qs = qs.all()
        elif busca_geral_uos in {"1", "true", "True"}:
            qs = qs.all()
        else:
            qs = filtrar_queryset_bem_por_escopo_com_transferencia(self.request.user, qs)

        baixa_data_sq = (
            BaixaFisicaBensItem.objects.filter(bem_id=OuterRef("pk"))
            .order_by("-baixa__data_baixa")
            .values("baixa__data_baixa")[:1]
        )
        qs = qs.annotate(baixa_data=Subquery(baixa_data_sq))

        if "baixados_mais_de_um_periodo" not in self.request.query_params:
            ano_corrente = timezone.localdate().year
            ano_limite = ano_corrente - 1
            qs = qs.exclude(
                status=constants.BAIXA_FISICA, baixa_data__year__lt=ano_limite
            )

        ct = ContentType.objects.get_for_model(BemPatrimonial)
        pk_as_char = Cast(OuterRef("pk"), output_field=models.CharField())
        hist_qs = HistoricoGeral.objects.filter(
            content_type=ct,
            object_id=pk_as_char,
        ).order_by("-alterado_em")

        qs = qs.annotate(
            audit_last_at=Subquery(hist_qs.values("alterado_em")[:1]),
            audit_last_by_id=Subquery(hist_qs.values("alterado_por_id")[:1]),
        )

        return qs

    def get_object(self):
        obj = super().get_object()

        action = getattr(self, "action", None)
        pode_visualizar_fora_escopo = action in {"retrieve", "historico"} and (
            getattr(self.request.user, "is_gestor_patrimonio", False)
            or getattr(self.request.user, "is_operador_inventario", False)
            or getattr(self.request.user, "is_superuser", False)
        )

        if (
            not pode_visualizar_fora_escopo
            and not validar_bem_no_escopo_com_transferencia(self.request.user, obj)
        ):
            from rest_framework.exceptions import NotFound

            raise NotFound()

        return obj

    def _save_with_audit(self, serializer):
        """Salva o serializer com contexto de auditoria (usado em create e update)."""
        with audit_as(self.request.user):
            serializer.save()

    def perform_create(self, serializer):
        self._save_with_audit(serializer)

    def perform_update(self, serializer):
        self._save_with_audit(serializer)

    def perform_destroy(self, instance):
        with audit_as(self.request.user):
            instance.delete()

    def _validar_gestor(self, request):
        if not (
            getattr(request.user, "is_gestor_patrimonio", False)
            or getattr(request.user, "is_superuser", False)
        ):
            raise PermissionDenied(
                "Você não tem permissão para executar esta ação. Restrito ao grupo GESTOR_PATRIMONIO."
            )

    def _get_queryset_escopo(self, request):
        return filtrar_queryset_por_escopo(
            usuario=request.user,
            queryset=BemPatrimonial.objects.all(),
            campo_ua="unidade_administrativa",
        )

    @action(detail=False, methods=["post"], url_path="multi")
    def create_multi(self, request):
        serializer = BemPatrimonialMultiCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        vdata = dict(serializer.validated_data)
        multi_payload = vdata.pop("multi_payload")
        base = vdata

        with transaction.atomic():
            with audit_as(request.user):
                bens = []
                for item in multi_payload:
                    sem = item.get("sem_numeracao", False)
                    bem = BemPatrimonial(
                        **base,
                        numero_patrimonial=(
                            None if sem else (item.get("numero_patrimonial") or None)
                        ),
                        numero_formato_antigo=item.get("numero_formato_antigo", False),
                        sem_numeracao=sem,
                        localizacao=item.get("localizacao", ""),
                        criado_por=request.user,
                        status=constants.AGUARDANDO_APROVACAO,
                    )
                    bem.save()
                    bens.append(bem)

        return Response(
            {
                "detail": f"{len(bens)} bem(ns) criado(s) com sucesso.",
                "count": len(bens),
            },
            status=http_status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="aprovar")
    def aprovar_bens(self, request):
        self._validar_gestor(request)

        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            raise DRFValidationError(
                {"ids": 'Envie uma lista de IDs. Ex.: {"ids": [1,2,3]}.'}
            )

        qs_base = self._get_queryset_escopo(request).filter(id__in=ids)

        bens_aguardando = qs_base.filter(status=constants.AGUARDANDO_APROVACAO)
        count_aguardando = bens_aguardando.count()
        count_outros = qs_base.exclude(status=constants.AGUARDANDO_APROVACAO).count()

        if count_aguardando == 0:
            return Response(
                {
                    "detail": "Nenhum bem selecionado está com status 'Aguardando aprovação'.",
                    "aprovados": 0,
                    "ignorados": count_outros,
                },
                status=http_status.HTTP_200_OK,
            )

        with transaction.atomic():
            with audit_as(request.user):
                ids_aguardando = list(bens_aguardando.values_list("id", flat=True))

                BemPatrimonial.objects.filter(id__in=ids_aguardando).update(
                    status=constants.APROVADO
                )

        return Response(
            {
                "detail": f"{count_aguardando} bem(ns) aprovado(s) com sucesso.",
                "aprovados": count_aguardando,
                "ignorados": count_outros,
            },
            status=http_status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="reprovar")
    def reprovar_bens(self, request):
        self._validar_gestor(request)

        ids = request.data.get("ids")
        if not isinstance(ids, list) or not ids:
            raise DRFValidationError(
                {"ids": 'Envie uma lista de IDs. Ex.: {"ids": [1,2,3]}.'}
            )

        qs_base = self._get_queryset_escopo(request).filter(id__in=ids)

        bens_aguardando = qs_base.filter(status=constants.AGUARDANDO_APROVACAO)
        count_aguardando = bens_aguardando.count()
        count_outros = qs_base.exclude(status=constants.AGUARDANDO_APROVACAO).count()

        if count_aguardando == 0:
            return Response(
                {
                    "detail": "Nenhum bem selecionado está com status 'Aguardando aprovação'.",
                    "reprovados": 0,
                    "ignorados": count_outros,
                },
                status=http_status.HTTP_200_OK,
            )

        with transaction.atomic():
            with audit_as(request.user):
                BemPatrimonial.objects.filter(
                    id__in=bens_aguardando.values_list("id", flat=True)
                ).update(status=constants.NAO_APROVADO)

        return Response(
            {
                "detail": f"{count_aguardando} bem(ns) reprovado(s) com sucesso.",
                "reprovados": count_aguardando,
                "ignorados": count_outros,
            },
            status=http_status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="historico")
    def historico(self, request, pk=None):
        bem = self.get_object()

        from django.contrib.contenttypes.models import ContentType
        from dados_comuns.models import HistoricoGeral

        ct = ContentType.objects.get_for_model(BemPatrimonial)

        historicos = (
            HistoricoGeral.objects.filter(content_type=ct, object_id=str(bem.pk))
            .select_related("alterado_por")
            .order_by("-alterado_em")
        )

        agrupado = defaultdict(list)

        for h in historicos:
            chave = (
                h.alterado_em.replace(microsecond=0),
                h.alterado_por_id,
            )
            agrupado[chave].append(h)

        resposta = []

        for (data, usuario_id), itens in agrupado.items():
            resposta.append(
                {
                    "alterado_em": data,
                    "alterado_por": usuario_id,
                    "alterado_por_nome": (
                        itens[0].alterado_por.nome if itens[0].alterado_por else None
                    ),
                    "acoes": [
                        {
                            "campo": i.campo,
                            "valor_antigo": i.valor_antigo,
                            "valor_novo": i.valor_novo,
                        }
                        for i in itens
                    ],
                }
            )

        resposta_ordenada = sorted(
            resposta, key=lambda x: x["alterado_em"], reverse=True
        )

        serializer = HistoricoGrupoSerializer(resposta_ordenada, many=True)
        return Response(serializer.data)
