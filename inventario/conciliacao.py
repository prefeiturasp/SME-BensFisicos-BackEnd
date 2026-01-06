from django.core.exceptions import ValidationError
from django.db import transaction

from bem_patrimonial import constants as bem_constants

from .models import ConciliacaoUA, ItemConciliacao, OcorrenciaConciliacao
from . import constants


@transaction.atomic
def registrar_ocorrencia(item, situacao, observacao="", divergencia="", usuario=None):
    if not item.conciliacao.esta_aberto:
        raise ValidationError("Inventário fechado não permite edições")

    if situacao == constants.DIVERGENTE and not divergencia:
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
            divergencia if situacao == constants.DIVERGENTE else ""
        )
        ultima_ocorrencia.save()
        ocorrencia = ultima_ocorrencia
    else:
        # Nova ocorrência: cria novo registro
        ocorrencia = OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=situacao,
            observacao=observacao,
            divergencia=divergencia if situacao == constants.DIVERGENTE else "",
            registrado_por=usuario,
        )

    item.situacao = situacao
    item.observacao = observacao
    item.divergencia = divergencia if situacao == constants.DIVERGENTE else ""
    item.atualizado_por = usuario
    item.save()

    if situacao == constants.NAO_ENCONTRADO:
        item.bem.bloqueado_conciliacao = True
        item.bem.save(update_fields=["bloqueado_conciliacao"])

    elif situacao in (constants.ENCONTRADO, constants.BAIXA_FISICA):
        item.bem.bloqueado_conciliacao = False
        item.bem.save(update_fields=["bloqueado_conciliacao"])

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
                status=constants.CONCILIACAO_FECHADO,
            )
            .exclude(pk=item.conciliacao.pk)
            .order_by("-criado_em")
            .first()
        )

        situacao_inicial = constants.ENCONTRADO_SEM_DIVERGENCIA
        divergencia_inicial = ""
        observacao_inicial = ""

        if conciliacao_anterior:
            item_anterior = ItemConciliacao.objects.filter(
                conciliacao=conciliacao_anterior, bem=item.bem
            ).first()
            if item_anterior and item_anterior.situacao in (
                constants.NAO_ENCONTRADO,
                constants.DIVERGENTE,
                constants.BAIXA_FISICA,
            ):
                situacao_inicial = item_anterior.situacao
                observacao_inicial = item_anterior.observacao

                if item_anterior.situacao == constants.DIVERGENTE:
                    divergencia_inicial = item_anterior.divergencia

        item.situacao = situacao_inicial
        item.observacao = observacao_inicial
        item.divergencia = divergencia_inicial

    item.atualizado_por = usuario
    item.save()

    item.bem.bloqueado_conciliacao = item.situacao == constants.NAO_ENCONTRADO
    item.bem.save(update_fields=["bloqueado_conciliacao"])


def finalizar_conciliacao(conciliacao, usuario):
    conciliacao.finalizar(usuario)
