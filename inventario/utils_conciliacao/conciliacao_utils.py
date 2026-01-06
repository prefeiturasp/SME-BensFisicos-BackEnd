from datetime import date

from django.db import transaction
from django.db.models import OuterRef, Subquery, Q
from django.utils import timezone

from bem_patrimonial.models import BemPatrimonial
from inventario.models import ConciliacaoUA, ItemConciliacao, OcorrenciaConciliacao
from inventario import constants

from bem_patrimonial import constants as bem_constants


def get_or_create_conciliacao(unidade_administrativa, usuario):
    ano = date.today().year
    conciliacao, created = ConciliacaoUA.objects.get_or_create(
        unidade_administrativa=unidade_administrativa,
        ano_referencia=ano,
        defaults={"criado_por": usuario},
    )

    if created:
        criar_itens_conciliacao(conciliacao)

    return conciliacao, created


def finalizar_conciliacao(conciliacao, usuario):
    conciliacao.finalizar(usuario)


def get_filtro_bens_baixados(ano_baixa_minimo):
    return Q(
        status=bem_constants.BAIXA_FISICA,
        baixas_fisicas_itens__baixa__status=bem_constants.ACEITA,
        baixas_fisicas_itens__baixa__data_baixa__year__gte=ano_baixa_minimo,
    )


def criar_itens_conciliacao(conciliacao):
    """
    - bens da UA
    - incluir bens ativos
    - incluir bens BAIXADOS apenas no ano anterior ao ano do inventário
      (ano da baixa = baixa_fisica.data_aprovacao, com baixa ACEITA)
    - Regra de herança de situação:
      * Se situação anterior foi NAO_ENCONTRADO, DIVERGENTE ou BAIXA_FISICA → herda situação, divergência e observação
      * Se situação anterior foi ENCONTRADO ou ENCONTRADO_SEM_DIVERGENCIA → inicia como ENCONTRADO_SEM_DIVERGENCIA
      * Se não tinha situação anterior → inicia como ENCONTRADO_SEM_DIVERGENCIA
    """

    if conciliacao.tipo == constants.CONCILIACAO_EVENTUAL:
        if not conciliacao.periodo_final:
            raise ValueError("Inventário eventual precisa de periodo_final.")
        ano_conciliacao = conciliacao.periodo_final.year - 1
    else:
        ano_conciliacao = conciliacao._get_ano_referencia()

    ano_baixa_minimo = ano_conciliacao - 1

    ultima_ocorrencia_base = OcorrenciaConciliacao.objects.filter(
        item__bem_id=OuterRef("pk"),
        item__conciliacao__status=constants.CONCILIACAO_FECHADO,
    ).order_by("-registrado_em")

    ultima_situacao_sq = ultima_ocorrencia_base.values("situacao")[:1]
    ultima_divergencia_sq = ultima_ocorrencia_base.values("divergencia")[:1]
    ultima_observacao_sq = ultima_ocorrencia_base.values("observacao")[:1]

    qs_bens = BemPatrimonial.objects.filter(
        unidade_administrativa=conciliacao.unidade_administrativa
    ).annotate(
        ultima_situacao_conciliacao=Subquery(ultima_situacao_sq),
        ultima_divergencia_conciliacao=Subquery(ultima_divergencia_sq),
        ultima_observacao_conciliacao=Subquery(ultima_observacao_sq),
    )

    filtro_ativos = ~Q(
        status__in=[
            bem_constants.BAIXA_FISICA,
            bem_constants.AGUARDANDO_APROVACAO,
        ]
    )

    filtro_baixados = get_filtro_bens_baixados(ano_baixa_minimo)

    bens = qs_bens.filter(filtro_ativos | filtro_baixados).distinct()
    situacoes_problematicas = (
        constants.NAO_ENCONTRADO,
        constants.DIVERGENTE,
        constants.BAIXA_FISICA,
    )

    itens = []
    for bem in bens:
        ultima_situacao = bem.ultima_situacao_conciliacao

        if ultima_situacao in situacoes_problematicas:
            situacao = ultima_situacao

            divergencia = (
                bem.ultima_divergencia_conciliacao
                if ultima_situacao == constants.DIVERGENTE
                else ""
            )
            observacao = bem.ultima_observacao_conciliacao or ""
        else:
            situacao = constants.ENCONTRADO_SEM_DIVERGENCIA
            divergencia = ""
            observacao = ""

        itens.append(
            ItemConciliacao(
                conciliacao=conciliacao,
                bem=bem,
                situacao=situacao,
                divergencia=divergencia,
                observacao=observacao,
            )
        )

    with transaction.atomic():
        ItemConciliacao.objects.filter(conciliacao=conciliacao).delete()
        ItemConciliacao.objects.bulk_create(itens, batch_size=1000)
