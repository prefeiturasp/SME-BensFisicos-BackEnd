from datetime import date
from django.core.exceptions import ValidationError
from django.db import transaction

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants as bem_constants

from .models import InventarioUA, ItemInventario, OcorrenciaInventario
from . import constants


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


def criar_itens_inventario(inventario):
    bens = BemPatrimonial.objects.filter(
        unidade_administrativa=inventario.unidade_administrativa,
        status=bem_constants.APROVADO,
    )

    situacoes_anteriores = {}
    inventario_anterior = None

    try:
        if inventario.tipo == constants.INVENTARIO_EVENTUAL:
            inventario_anterior = (
                InventarioUA.objects.filter(
                    unidade_administrativa=inventario.unidade_administrativa,
                )
                .exclude(pk=inventario.pk)
                .order_by("-ano_referencia", "-versao")
                .first()
            )
        else:
            ano_anterior = inventario.ano_referencia - 1
            inventario_anterior = InventarioUA.objects.filter(
                unidade_administrativa=inventario.unidade_administrativa,
                ano_referencia=ano_anterior,
                tipo=constants.INVENTARIO_ANUAL,
            ).first()

        if inventario_anterior:
            situacoes_anteriores = dict(
                ItemInventario.objects.filter(
                    inventario=inventario_anterior
                ).values_list("bem_id", "situacao")
            )
    except Exception:
        pass

    itens = [
        ItemInventario(
            inventario=inventario,
            bem=bem,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
            situacao_anterior=situacoes_anteriores.get(bem.id),
        )
        for bem in bens
    ]

    ItemInventario.objects.bulk_create(itens)


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


def finalizar_inventario(inventario, usuario):
    inventario.finalizar(usuario)
