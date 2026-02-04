from django.utils import timezone
from datetime import date
from collections import defaultdict

from inventario.models import ConciliacaoUA, ParametroConciliacaoAnual
from dados_comuns.models import UnidadeAdministrativa
from inventario import constants
from inventario.utils_conciliacao.conciliacao_utils import (
    criar_itens_conciliacao,
)


def fechar_pelo_sistema(conciliacao):
    conciliacao.status = constants.CONCILIACAO_FECHADO_ADMIN
    conciliacao.fechado_por = None
    conciliacao.fechado_em = timezone.now()
    conciliacao.save(update_fields=["status", "fechado_por", "fechado_em"])


def criar_conciliacao_anual(ua, ano_referencia):
    if not unidade_possui_bens(ua):
        return

    if ConciliacaoUA.objects.filter(
        unidade_administrativa=ua,
        tipo=constants.CONCILIACAO_ANUAL,
        periodo_final=date(ano_referencia, 12, 31),
    ).exists():
        return

    conciliacao = ConciliacaoUA.objects.create(
        unidade_administrativa=ua,
        tipo=constants.CONCILIACAO_ANUAL,
        criado_por=None,
    )

    criar_itens_conciliacao(conciliacao)


def unidade_possui_bens(ua):
    return ua.bems_patrimonial.exists()


def processar_conciliacao_anual_automatica(usuario):
    if usuario.is_gestor_patrimonio:
        ua_usuario = getattr(usuario, "unidade_administrativa", None)
        if ua_usuario:
            unidades = [ua_usuario]
        else:
            unidades = UnidadeAdministrativa.objects.filter(
                status=UnidadeAdministrativa.ATIVA
            )
    else:
        ua = getattr(usuario, "unidade_administrativa", None)
        if not ua:
            return
        unidades = [ua]

    hoje = timezone.localdate()
    ano_corrente = hoje.year
    ano_referencia = ano_corrente - 1

    por_uo = defaultdict(list)
    for ua in unidades:
        uo_id = getattr(ua, "unidade_orcamentaria_id", None)
        por_uo[uo_id].append(ua)

    for uo_id, uas in por_uo.items():

        parametro = ParametroConciliacaoAnual.objects.filter(
            unidade_orcamentaria_id=uo_id,
            ano_referencia=ano_referencia,
            ativo=True,
        ).first()

        if parametro:
            inicio = parametro.periodo_inicial
            fim = parametro.periodo_final
        else:
            inicio = date(ano_corrente, 1, 1)
            fim = date(ano_corrente, 3, 31)

        for ua in uas:
            anual_existente = ConciliacaoUA.objects.filter(
                unidade_administrativa=ua,
                tipo=constants.CONCILIACAO_ANUAL,
                periodo_final=date(ano_referencia, 12, 31),
            ).first()

            eventual_aberta = ConciliacaoUA.objects.filter(
                unidade_administrativa=ua,
                tipo=constants.CONCILIACAO_EVENTUAL,
                status=constants.CONCILIACAO_EM_ABERTO,
            ).first()

            if inicio <= hoje <= fim:
                if eventual_aberta and not anual_existente:
                    fechar_pelo_sistema(eventual_aberta)

                if not anual_existente:
                    criar_conciliacao_anual(ua, ano_referencia)

            elif hoje > fim:
                anual_aberta = ConciliacaoUA.objects.filter(
                    unidade_administrativa=ua,
                    tipo=constants.CONCILIACAO_ANUAL,
                    status=constants.CONCILIACAO_EM_ABERTO,
                ).first()
                if anual_aberta:
                    fechar_pelo_sistema(anual_aberta)
