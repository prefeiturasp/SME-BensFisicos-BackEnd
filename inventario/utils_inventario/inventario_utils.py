from datetime import date

from django.db import transaction
from django.db.models import OuterRef, Subquery, Q
from django.utils import timezone

from bem_patrimonial.models import BemPatrimonial
from inventario.models import InventarioUA, ItemInventario, OcorrenciaInventario
from inventario import constants

from bem_patrimonial import constants as bem_constants


def get_or_create_inventario(unidade_administrativa, usuario):
    ano = date.today().year
    inventario, created = InventarioUA.objects.get_or_create(
        unidade_administrativa=unidade_administrativa,
        ano_referencia=ano,
        defaults={"criado_por": usuario},
    )

    if created:
        criar_itens_inventario(inventario)

    return inventario, created


def finalizar_inventario(inventario, usuario):
    inventario.finalizar(usuario)


def criar_itens_inventario(inventario):
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
    hoje = timezone.localdate()

    if inventario.tipo == constants.INVENTARIO_EVENTUAL:
        if not inventario.periodo_final:
            raise ValueError("Inventário eventual precisa de periodo_final.")
        ano_inventario = inventario.periodo_final.year
    else:

        ano_inventario = hoje.year

    ano_baixa_minimo = ano_inventario - 1

    ultima_ocorrencia_base = OcorrenciaInventario.objects.filter(
        item__bem_id=OuterRef("pk"),
        item__inventario__status=constants.INVENTARIO_FECHADO,
    ).order_by("-registrado_em")

    ultima_situacao_sq = ultima_ocorrencia_base.values("situacao")[:1]
    ultima_divergencia_sq = ultima_ocorrencia_base.values("divergencia")[:1]
    ultima_observacao_sq = ultima_ocorrencia_base.values("observacao")[:1]

    qs_bens = BemPatrimonial.objects.filter(
        unidade_administrativa=inventario.unidade_administrativa
    ).annotate(
        ultima_situacao_inventario=Subquery(ultima_situacao_sq),
        ultima_divergencia_inventario=Subquery(ultima_divergencia_sq),
        ultima_observacao_inventario=Subquery(ultima_observacao_sq),
    )

    filtro_ativos = ~Q(
        status__in=[
            bem_constants.BAIXA_FISICA,
            bem_constants.AGUARDANDO_APROVACAO,
        ]
    )

    filtro_baixados_a_partir_do_ano_anterior = Q(
        status=bem_constants.BAIXA_FISICA,
        baixas_fisicas_itens__baixa__status=bem_constants.ACEITA,
        baixas_fisicas_itens__baixa__data_aprovacao__year__gte=ano_baixa_minimo,
    )

    bens = qs_bens.filter(filtro_ativos | filtro_baixados_a_partir_do_ano_anterior).distinct()

    situacoes_problematicas = (
        constants.NAO_ENCONTRADO,
        constants.DIVERGENTE,
        constants.BAIXA_FISICA,
    )

    itens = []
    for bem in bens:
        ultima_situacao = bem.ultima_situacao_inventario

        if ultima_situacao in situacoes_problematicas:
            situacao = ultima_situacao

            divergencia = (
                bem.ultima_divergencia_inventario
                if ultima_situacao == constants.DIVERGENTE
                else ""
            )
            observacao = bem.ultima_observacao_inventario or ""
        else:
            situacao = constants.ENCONTRADO_SEM_DIVERGENCIA
            divergencia = ""
            observacao = ""

        itens.append(
            ItemInventario(
                inventario=inventario,
                bem=bem,
                situacao=situacao,
                divergencia=divergencia,
                observacao=observacao,
            )
        )

    with transaction.atomic():
        ItemInventario.objects.filter(inventario=inventario).delete()
        ItemInventario.objects.bulk_create(itens, batch_size=1000)
