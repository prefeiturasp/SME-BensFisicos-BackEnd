from django.core.exceptions import ValidationError
from django.db import transaction

from bem_patrimonial import constants as bem_constants

from .models import InventarioUA, ItemInventario, OcorrenciaInventario
from . import constants


@transaction.atomic
def registrar_ocorrencia(item, situacao, observacao="", divergencia="", usuario=None):
    if not item.inventario.esta_aberto:
        raise ValidationError("Inventário fechado não permite edições")

    if situacao == constants.DIVERGENTE and not divergencia:
        raise ValidationError(
            "Campo divergência é obrigatório quando situação é Divergente"
        )

    ultima_ocorrencia = item.ocorrencias.order_by("-registrado_em").first()

    if ultima_ocorrencia and ultima_ocorrencia.situacao == situacao:
        ultima_ocorrencia.observacao = observacao
        ultima_ocorrencia.divergencia = (
            divergencia if situacao == constants.DIVERGENTE else ""
        )
        ultima_ocorrencia.save()
        ocorrencia = ultima_ocorrencia
    else:
        ocorrencia = OcorrenciaInventario.objects.create(
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
        inventario_anterior = (
            InventarioUA.objects.filter(
                unidade_administrativa=item.inventario.unidade_administrativa,
                status=constants.INVENTARIO_FECHADO,
            )
            .exclude(pk=item.inventario.pk)
            .order_by("-criado_em")
            .first()
        )

        situacao_inicial = constants.ENCONTRADO_SEM_DIVERGENCIA
        divergencia_inicial = ""
        observacao_inicial = ""

        if inventario_anterior:
            item_anterior = ItemInventario.objects.filter(
                inventario=inventario_anterior, bem=item.bem
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

    item.bem.bloqueado_inventario = item.situacao == constants.NAO_ENCONTRADO
    item.bem.save(update_fields=["bloqueado_inventario"])


def finalizar_inventario(inventario, usuario):
    inventario.finalizar(usuario)
