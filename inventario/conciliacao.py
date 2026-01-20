from django.core.exceptions import ValidationError
from django.db import transaction

from .models import ConciliacaoUA, ItemConciliacao, OcorrenciaConciliacao
from . import constants as inv_constants
from bem_patrimonial import constants as bem_constants
from bem_patrimonial.models import BemPatrimonial


def _recalcular_bloqueio_bem_por_inventario(bem: BemPatrimonial):
    """
    Bloqueia o bem se existir QUALQUER ItemConciliacao em conciliação EM ABERTO
    com situação EM_PROCESSO_BAIXA_FISICA para este bem.

    Desbloqueia caso contrário (desde que o bem ainda esteja APROVADO, porque se estiver BAIXA_FISICA,
    já não pode movimentar mesmo).
    """
    existe_bloqueio_em_aberto = ItemConciliacao.objects.filter(
        bem_id=bem.pk,
        conciliacao__status=inv_constants.CONCILIACAO_EM_ABERTO,
        situacao__in=[
            inv_constants.NAO_ENCONTRADO,
            inv_constants.EM_PROCESSO_BAIXA_FISICA,
        ],
    ).exists()

    novo_valor = bool(existe_bloqueio_em_aberto)

    if bem.status == bem_constants.BAIXA_FISICA:
        novo_valor = False

    if bem.bloqueado_conciliacao != novo_valor:
        bem.bloqueado_conciliacao = novo_valor
        bem.save(update_fields=["bloqueado_conciliacao"])


@transaction.atomic
def registrar_ocorrencia(item, situacao, observacao="", divergencia="", usuario=None):
    if not item.conciliacao.esta_aberto:
        raise ValidationError("Inventário fechado não permite edições")

    if situacao == inv_constants.DIVERGENTE and not divergencia:
        raise ValidationError(
            "Campo divergência é obrigatório quando situação é Divergente"
        )

    # Se já tem ocorrência, estamos editando - atualiza a última ao invés de criar nova
    ultima_ocorrencia = item.ocorrencias.order_by("-registrado_em").first()

    if ultima_ocorrencia:
        # Edição: atualiza a última ocorrência existente
        ultima_ocorrencia.situacao = situacao
        ultima_ocorrencia.observacao = observacao
        ultima_ocorrencia.divergencia = (
            divergencia if situacao == inv_constants.DIVERGENTE else ""
        )
        ultima_ocorrencia.save()
        ocorrencia = ultima_ocorrencia
    else:
        # Nova ocorrência: cria novo registro
        ocorrencia = OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=situacao,
            observacao=observacao,
            divergencia=divergencia if situacao == inv_constants.DIVERGENTE else "",
            registrado_por=usuario,
        )

    item.situacao = situacao
    item.observacao = observacao
    item.divergencia = divergencia if situacao == inv_constants.DIVERGENTE else ""
    item.atualizado_por = usuario
    item.save(update_fields=["situacao", "observacao", "divergencia", "atualizado_por"])

    _recalcular_bloqueio_bem_por_inventario(item.bem)

    return ocorrencia


@transaction.atomic
def excluir_ocorrencia(item, usuario):
    if not item.conciliacao.esta_aberto:
        raise ValidationError("Inventário fechado não permite edições")

    ultima_ocorrencia = item.ocorrencias.order_by("-registrado_em").first()
    if not ultima_ocorrencia:
        raise ValidationError("Item não tem ocorrência para excluir")

    ocorrencia_anterior = (
        item.ocorrencias.filter(registrado_em__lt=ultima_ocorrencia.registrado_em)
        .order_by("-registrado_em")
        .first()
    )

    ultima_ocorrencia.delete()

    if ocorrencia_anterior:
        item.situacao = ocorrencia_anterior.situacao
        item.observacao = ocorrencia_anterior.observacao
        item.divergencia = ocorrencia_anterior.divergencia
    else:
        conciliacao_anterior = (
            ConciliacaoUA.objects.filter(
                unidade_administrativa=item.conciliacao.unidade_administrativa,
                status=inv_constants.CONCILIACAO_FECHADO,
            )
            .exclude(pk=item.conciliacao.pk)
            .order_by("-criado_em")
            .first()
        )

        situacao_inicial = inv_constants.ENCONTRADO_SEM_DIVERGENCIA
        divergencia_inicial = ""
        observacao_inicial = ""

        if conciliacao_anterior:
            item_anterior = ItemConciliacao.objects.filter(
                conciliacao=conciliacao_anterior, bem=item.bem
            ).first()
            if item_anterior and item_anterior.situacao in (
                inv_constants.NAO_ENCONTRADO,
                inv_constants.DIVERGENTE,
                inv_constants.BAIXA_FISICA,
                inv_constants.EM_PROCESSO_BAIXA_FISICA,
            ):
                situacao_inicial = item_anterior.situacao
                observacao_inicial = item_anterior.observacao

                if item_anterior.situacao == inv_constants.DIVERGENTE:
                    divergencia_inicial = item_anterior.divergencia

        item.situacao = situacao_inicial
        item.observacao = observacao_inicial
        item.divergencia = divergencia_inicial

    item.atualizado_por = usuario
    item.save()

    _recalcular_bloqueio_bem_por_inventario(item.bem)


def finalizar_conciliacao(conciliacao, usuario):
    conciliacao.finalizar(usuario)
