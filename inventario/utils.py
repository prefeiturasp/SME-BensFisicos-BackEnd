from datetime import date
from django.core.exceptions import ValidationError
from django.db import transaction

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants as bem_constants

from .models import InventarioUA, ItemInventario, OcorrenciaInventario
from . import constants


@transaction.atomic
def registrar_ocorrencia(item, situacao, observacao="", divergencia="", usuario=None):
    if not item.inventario.esta_aberto:
        raise ValidationError("Inventário fechado não permite edições")

    if (
        situacao == constants.ENCONTRADO
        and item.situacao_anterior != constants.NAO_ENCONTRADO
    ):
        raise ValidationError(
            'Opção "Encontrado" só disponível se situação anterior era "Não encontrado"'
        )

    if situacao == constants.DIVERGENTE and not divergencia:
        raise ValidationError(
            "Campo divergência é obrigatório quando situação é Divergente"
        )

    situacao_antes = item.situacao

    item.situacao = situacao
    item.observacao = observacao
    item.divergencia = divergencia if situacao == constants.DIVERGENTE else ""
    item.atualizado_por = usuario
    item.save()

    ocorrencia = OcorrenciaInventario.objects.create(
        item=item,
        situacao_anterior=situacao_antes,
        situacao_nova=situacao,
        observacao=observacao,
        divergencia=item.divergencia,
        registrado_por=usuario,
    )

    if situacao == constants.NAO_ENCONTRADO:
        item.bem.bloqueado_inventario = True
        item.bem.save(update_fields=["bloqueado_inventario"])

    elif situacao in (constants.ENCONTRADO, constants.BAIXA_FISICA):
        item.bem.bloqueado_inventario = False
        item.bem.save(update_fields=["bloqueado_inventario"])

    return ocorrencia


@transaction.atomic
def excluir_ocorrencia(item, usuario):
    if not item.inventario.esta_aberto:
        raise ValidationError("Inventário fechado não permite edições")

    if item.situacao == constants.ENCONTRADO_SEM_DIVERGENCIA:
        raise ValidationError("Item não tem ocorrência registrada para excluir")

    situacao_antes = item.situacao

    item.situacao = constants.ENCONTRADO_SEM_DIVERGENCIA
    item.observacao = ""
    item.divergencia = ""
    item.atualizado_por = usuario
    item.save()

    ocorrencia = OcorrenciaInventario.objects.create(
        item=item,
        situacao_anterior=situacao_antes,
        situacao_nova=constants.ENCONTRADO_SEM_DIVERGENCIA,
        observacao="Ocorrência excluída",
        divergencia="",
        registrado_por=usuario,
    )

    item.bem.bloqueado_inventario = False
    item.bem.save(update_fields=["bloqueado_inventario"])

    return ocorrencia
