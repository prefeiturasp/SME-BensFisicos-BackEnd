from django.db import transaction

from bem_patrimonial import constants as bem_constants
from dados_comuns.context import get_user
from inventario import constants as inv_constants
from inventario.models import ConciliacaoUA, ItemConciliacao, OcorrenciaConciliacao


def _conciliacoes_em_aberto(ua_id):
    if not ua_id:
        return ConciliacaoUA.objects.none()

    return ConciliacaoUA.objects.filter(unidade_administrativa_id=ua_id, status=inv_constants.CONCILIACAO_EM_ABERTO)


def _status_pendente_acao(bem):
    pendentes = set()
    pendentes.add(getattr(bem_constants, "BLOQUEADO", None))
    pendentes.add(getattr(bem_constants, "BAIXA_FISICA_AGUARDANDO_APROVACAO", None))
    pendentes.add(getattr(bem_constants, "AGUARDANDO_APROVACAO", None))

    pendentes.discard(None)
    return bem.status in pendentes


def _tem_em_processo_baixa(bem_id, ua_id):
    if not ua_id:
        return False

    return OcorrenciaConciliacao.objects.filter(
        item__bem_id=bem_id,
        item__conciliacao__unidade_administrativa_id=ua_id,
        item__conciliacao__status=inv_constants.CONCILIACAO_EM_ABERTO,
        situacao=inv_constants.EM_PROCESSO_BAIXA_FISICA,
    ).exists()


@transaction.atomic
def remover_bem_de_conciliacoes_em_aberto(bem_id, ua_id):
    if not ua_id:
        return

    ItemConciliacao.objects.filter(bem_id=bem_id, conciliacao__in=_conciliacoes_em_aberto(ua_id)).delete()


def _processar_item_laudado(item, usuario):
    # Bem laudado para baixa (fluxo novo): leitura distinta do processo
    # de baixa comum, sem tratar como bem normal. Preserva somente se o
    # estado atual já é EM_PROCESSO, senão força EM_PROCESSO zerado.
    # Preserva ocorrências antigas para auditoria: registrar/excluir já
    # bloqueiam divergente para laudado, sem bypass.
    ultima_ocorrencia = OcorrenciaConciliacao.objects.filter(item=item).order_by("-registrado_em").first()
    if (
        item.situacao == inv_constants.EM_PROCESSO_BAIXA_FISICA
        and ultima_ocorrencia is not None
        and ultima_ocorrencia.situacao == inv_constants.EM_PROCESSO_BAIXA_FISICA
    ):
        return
    if (
        item.situacao != inv_constants.EM_PROCESSO_BAIXA_FISICA
        or (item.observacao or "") != ""
        or (item.divergencia or "") != ""
    ):
        item.situacao = inv_constants.EM_PROCESSO_BAIXA_FISICA
        item.observacao = ""
        item.divergencia = ""
        item.atualizado_por = usuario
        item.save(
            update_fields=[
                "situacao",
                "observacao",
                "divergencia",
                "atualizado_por",
                "atualizado_em",
            ]
        )


def _marcar_item_encontrado(item, usuario):
    OcorrenciaConciliacao.objects.filter(item=item).exclude(situacao=inv_constants.EM_PROCESSO_BAIXA_FISICA).delete()

    item.situacao = inv_constants.ENCONTRADO_SEM_DIVERGENCIA
    item.observacao = ""
    item.divergencia = ""
    item.atualizado_por = usuario
    item.save(
        update_fields=[
            "situacao",
            "observacao",
            "divergencia",
            "atualizado_por",
            "atualizado_em",
        ]
    )


def _atualizar_bloqueio_pos_sync(bem, em_processo):
    if bem.status in bem_constants.STATUS_FINAIS_BEM:
        # Status final (laudado, baixa_fisica, transferido): sem bloqueio
        # por conciliação, igual a _recalcular_bloqueio_bem_por_inventario.
        bem.__class__.objects.filter(pk=bem.pk).update(bloqueado_conciliacao=False)
    else:
        bem.__class__.objects.filter(pk=bem.pk).update(bloqueado_conciliacao=em_processo)


@transaction.atomic
def incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(bem, ua_id):
    if not ua_id:
        return

    usuario = get_user()
    conciliacoes = _conciliacoes_em_aberto(ua_id)

    pendente = _status_pendente_acao(bem)
    em_processo = _tem_em_processo_baixa(bem.pk, ua_id)
    eh_laudado = bem.status == bem_constants.LAUDADO_PARA_BAIXA

    for conciliacao in conciliacoes:
        item, _ = ItemConciliacao.objects.get_or_create(
            conciliacao=conciliacao,
            bem=bem,
            defaults={
                "situacao": inv_constants.ENCONTRADO_SEM_DIVERGENCIA,
                "observacao": "",
                "divergencia": "",
                "atualizado_por": usuario,
            },
        )

        if eh_laudado:
            _processar_item_laudado(item, usuario)
            continue

        if pendente:
            continue

        if em_processo:
            # Item com ocorrência "Em processo de baixa" já reflete o que o
            # usuário salvou em registrar_ocorrencia. Este sync é disparado
            # via on_commit quando bem.save() muda bloqueado_conciliacao;
            # sobrescrever aqui reverteria o registro recém-feito.
            continue

        _marcar_item_encontrado(item, usuario)

    _atualizar_bloqueio_pos_sync(bem, em_processo)


@transaction.atomic
def sync_bem_pos_save(bem, old_ua_id=None):
    new_ua_id = bem.unidade_administrativa_id

    if getattr(bem, "excluido", False):
        remover_bem_de_conciliacoes_em_aberto(bem.pk, new_ua_id)
        return

    if bem.status == bem_constants.TRANSFERIDO:
        if old_ua_id and old_ua_id != new_ua_id:
            remover_bem_de_conciliacoes_em_aberto(bem.pk, old_ua_id)
        remover_bem_de_conciliacoes_em_aberto(bem.pk, new_ua_id)
        bem.__class__.objects.filter(pk=bem.pk).update(bloqueado_conciliacao=False)
        return

    if old_ua_id and old_ua_id != new_ua_id:
        remover_bem_de_conciliacoes_em_aberto(bem.pk, old_ua_id)

        if _conciliacoes_em_aberto(new_ua_id).exists():
            incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(bem, new_ua_id)

        return

    if _conciliacoes_em_aberto(new_ua_id).exists():
        incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(bem, new_ua_id)
