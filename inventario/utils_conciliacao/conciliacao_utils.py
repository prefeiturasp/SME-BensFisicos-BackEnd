from datetime import date

from django.db import transaction
from django.db.models import OuterRef, Q, Subquery
from django.utils import timezone

from bem_patrimonial import constants as bem_constants
from bem_patrimonial.models import BaixaFisicaBensItem, BemPatrimonial
from inventario import constants
from inventario.models import ConciliacaoUA, ItemConciliacao, OcorrenciaConciliacao


def _get_ano_referencia_conciliacao(conciliacao):
    if conciliacao.tipo == constants.CONCILIACAO_EVENTUAL:
        return conciliacao.periodo_final.year if conciliacao.periodo_final else timezone.localdate().year
    return conciliacao._get_ano_referencia()


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


@transaction.atomic
def _confirmar_baixas_fisicas_pos_conciliacao(conciliacao, usuario):
    ano_ref = _get_ano_referencia_conciliacao(conciliacao)

    itens = ItemConciliacao.objects.filter(
        conciliacao=conciliacao, situacao=constants.EM_PROCESSO_BAIXA_FISICA
    ).select_related("bem")

    if not itens.exists():
        return 0

    bem_ids = list(itens.values_list("bem_id", flat=True))

    bem_ids_confirmados = set(
        BaixaFisicaBensItem.objects.filter(
            bem_id__in=bem_ids,
            baixa__status=bem_constants.ACEITA,
            baixa__data_baixa__year=ano_ref,
        ).values_list("bem_id", flat=True)
    )

    if not bem_ids_confirmados:
        return 0

    ocorrencias = []
    itens_para_atualizar = []

    for item in itens:
        if item.bem_id not in bem_ids_confirmados:
            continue

        # Laudado para baixa (fluxo novo) ainda aguarda a baixa final (NBBPM):
        # não confirma como baixa física no fechamento.
        if getattr(item.bem, "status", None) == bem_constants.LAUDADO_PARA_BAIXA:
            continue

        ocorrencias.append(
            OcorrenciaConciliacao(
                item=item,
                situacao=constants.BAIXA_FISICA,
                observacao="Baixa Física confirmada automaticamente após fechamento da conciliação.",
                divergencia="",
                registrado_por=usuario,
            )
        )

        item.situacao = constants.BAIXA_FISICA
        item.observacao = "Baixa Física confirmada automaticamente após fechamento da conciliação."
        item.divergencia = ""
        itens_para_atualizar.append(item)

    if ocorrencias:
        OcorrenciaConciliacao.objects.bulk_create(ocorrencias, batch_size=500)

    if itens_para_atualizar:
        ItemConciliacao.objects.bulk_update(
            itens_para_atualizar, ["situacao", "observacao", "divergencia"], batch_size=500
        )
        BemPatrimonial.objects.filter(pk__in=[item.bem_id for item in itens_para_atualizar]).update(
            bloqueado_conciliacao=False
        )

    return len(ocorrencias)


def finalizar_conciliacao(conciliacao, usuario):
    from inventario.conciliacao import _recalcular_bloqueio_bem_por_inventario

    conciliacao.finalizar(usuario)
    _confirmar_baixas_fisicas_pos_conciliacao(conciliacao, usuario)
    # Pós-fechamento: esta conciliação saiu de em_aberto, então itens
    # EM_PROCESSO não confirmados não podem manter bloqueio preso.
    # Recalcula por bem (respeita outra aberta com EM_PROCESSO e finais).
    bem_ids = list(ItemConciliacao.objects.filter(conciliacao=conciliacao).values_list("bem_id", flat=True).distinct())
    for bem in BemPatrimonial.objects.filter(pk__in=bem_ids):
        _recalcular_bloqueio_bem_por_inventario(bem)


def get_filtro_bens_baixados(ano_baixa_minimo):
    return Q(
        status=bem_constants.BAIXA_FISICA,
        baixas_fisicas_itens__baixa__status=bem_constants.ACEITA,
        baixas_fisicas_itens__baixa__data_baixa__year__gte=ano_baixa_minimo,
    )


def remover_itens_baixados_invalidos(conciliacao):
    """
    Remove da conciliação aberta os itens cujos bens foram baixados a mais de
    um período, ou seja, cuja data_baixa é anterior ao ano de referência da
    conciliação. Conciliações fechadas não são alteradas.
    Retorna o número de itens removidos.
    """
    if not conciliacao.esta_aberto:
        return 0

    if conciliacao.tipo == constants.CONCILIACAO_EVENTUAL:
        if not conciliacao.periodo_final:
            return 0
        ano_conciliacao = conciliacao.periodo_final.year - 1
    else:
        ano_conciliacao = conciliacao._get_ano_referencia()

    ano_baixa_minimo = ano_conciliacao

    itens_invalidos = ItemConciliacao.objects.filter(
        conciliacao=conciliacao,
        bem__status=bem_constants.BAIXA_FISICA,
    ).exclude(
        bem__baixas_fisicas_itens__baixa__status=bem_constants.ACEITA,
        bem__baixas_fisicas_itens__baixa__data_baixa__year__gte=ano_baixa_minimo,
    )

    count, _ = itens_invalidos.delete()
    return count


def criar_itens_conciliacao(conciliacao):
    """
    - bens da UA
    - incluir bens ativos
    - incluir bens BAIXADOS apenas no ano anterior ao ano do inventário
      (ano da baixa = baixa_fisica.data_aprovacao, com baixa ACEITA)
    - bens LAUDADOS PARA BAIXA (fluxo novo da baixa física) são incluídos como
      ativos e têm leitura distinta: item em processo de baixa, com status do
      bem exposto para a tela distinguir do processo de baixa comum.
    - Regra de herança de situação:
      * Se situação anterior foi NAO_ENCONTRADO, DIVERGENTE ou BAIXA_FISICA → herda situação, divergência e observação
      * Se situação anterior foi ENCONTRADO ou ENCONTRADO_SEM_DIVERGENCIA → inicia como ENCONTRADO_SEM_DIVERGENCIA
      * Se não tinha situação anterior → inicia como ENCONTRADO_SEM_DIVERGENCIA
      * Bem laudado para baixa -> sempre EM_PROCESSO_BAIXA_FISICA (não trata como bem normal)
    - Só cria em conciliação aberta. Fechada não muda.
    """

    if not conciliacao.esta_aberto:
        return

    # Proteção básica: criar só uma vez. Se já tem itens, não recria para
    # não apagar ocorrências registradas pelo usuário em aberta.
    if ItemConciliacao.objects.filter(conciliacao=conciliacao).exists():
        return

    if conciliacao.tipo == constants.CONCILIACAO_EVENTUAL:
        if not conciliacao.periodo_final:
            raise ValueError("Inventário eventual precisa de periodo_final.")
        ano_conciliacao = conciliacao.periodo_final.year - 1
    else:
        ano_conciliacao = conciliacao._get_ano_referencia()

    ano_baixa_minimo = ano_conciliacao

    ultima_ocorrencia_base = OcorrenciaConciliacao.objects.filter(
        item__bem_id=OuterRef("pk"),
        item__conciliacao__status=constants.CONCILIACAO_FECHADO,
    ).order_by("-registrado_em")

    ultima_situacao_sq = ultima_ocorrencia_base.values("situacao")[:1]
    ultima_divergencia_sq = ultima_ocorrencia_base.values("divergencia")[:1]
    ultima_observacao_sq = ultima_ocorrencia_base.values("observacao")[:1]

    qs_bens = BemPatrimonial.objects.filter(unidade_administrativa=conciliacao.unidade_administrativa).annotate(
        ultima_situacao_conciliacao=Subquery(ultima_situacao_sq),
        ultima_divergencia_conciliacao=Subquery(ultima_divergencia_sq),
        ultima_observacao_conciliacao=Subquery(ultima_observacao_sq),
    )

    filtro_ativos = ~Q(
        status__in=[
            bem_constants.BAIXA_FISICA,
            bem_constants.AGUARDANDO_APROVACAO,
            bem_constants.TRANSFERIDO,
        ]
    )
    # LAUDADO_PARA_BAIXA permanece no filtro de ativos: o bem laudado continua
    # na conciliação aberta com leitura distinta do processo de baixa comum.

    filtro_baixados = get_filtro_bens_baixados(ano_baixa_minimo)

    bens = qs_bens.filter(filtro_ativos | filtro_baixados).distinct()
    situacoes_problematicas = (
        constants.NAO_ENCONTRADO,
        constants.DIVERGENTE,
        constants.BAIXA_FISICA,
        constants.EM_PROCESSO_BAIXA_FISICA,
    )

    itens = []
    for bem in bens:
        ultima_situacao = bem.ultima_situacao_conciliacao

        if bem.status == bem_constants.LAUDADO_PARA_BAIXA:
            situacao = constants.EM_PROCESSO_BAIXA_FISICA
            divergencia = ""
            observacao = ""
        elif ultima_situacao in situacoes_problematicas:
            situacao = ultima_situacao

            divergencia = bem.ultima_divergencia_conciliacao if ultima_situacao == constants.DIVERGENTE else ""
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
