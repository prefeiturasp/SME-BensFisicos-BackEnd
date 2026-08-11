from __future__ import annotations

from typing import Any

from dados_comuns.context import audit_as
from django.db import transaction
from django.urls import reverse
from rest_framework import serializers

from bem_patrimonial import constants
from bem_patrimonial.models import (
    BemPatrimonial,
    TransferenciaBemPatrimonial,
    TransferenciaBensItem,
)
from bem_patrimonial.serializers.movimentacao_serializers import (
    BemPatrimonialSimpleSerializer,
    UnidadeAdministrativaSimpleSerializer,
    UnidadeOrcamentariaSimpleSerializer,
    UserSimpleSerializer,
    obter_ua_ponto_central,
    obter_uo_referencia_do_usuario,
)
from dados_comuns.models import UnidadeOrcamentaria
from dados_comuns.utils import PREFIXO_CODIGO_UO_SME, unidade_orcamentaria_eh_externa

MENSAGEM_SEM_PONTO_CENTRAL = (
    "Não há ponto central cadastrado na Unidade Orçamentária de destino. "
    "Por favor, entrar em contato com o gestor."
)


def queryset_uos_destino_externas(uo_origem_id: int | None = None):
    qs = UnidadeOrcamentaria.objects.filter(ativa=True).exclude(
        codigo__startswith=PREFIXO_CODIGO_UO_SME
    )

    if uo_origem_id:
        qs = qs.exclude(pk=uo_origem_id)

    return qs.order_by("codigo", "nome")


class TransferenciaUoCadastroOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    codigo = serializers.CharField()
    nome = serializers.CharField()
    label = serializers.CharField()
    tem_ponto_central = serializers.BooleanField()


class TransferenciaBensItemSimpleSerializer(serializers.ModelSerializer):
    bem = BemPatrimonialSimpleSerializer(read_only=True)

    class Meta:
        model = TransferenciaBensItem
        fields = ["id", "bem"]
        read_only_fields = fields


class TransferenciaBensItemCreateSerializer(serializers.Serializer):
    bem = serializers.PrimaryKeyRelatedField(
        queryset=BemPatrimonial.objects.select_related("unidade_administrativa")
    )


class TransferenciaBemPatrimonialBaseSerializer(serializers.ModelSerializer):
    unidade_orcamentaria_origem = UnidadeOrcamentariaSimpleSerializer(read_only=True)
    unidade_orcamentaria_destino = UnidadeOrcamentariaSimpleSerializer(read_only=True)
    unidade_administrativa_destino = UnidadeAdministrativaSimpleSerializer(read_only=True)
    criado_por = UserSimpleSerializer(read_only=True)
    total_itens = serializers.SerializerMethodField()
    url_documento_ntbpm = serializers.SerializerMethodField()

    class Meta:
        model = TransferenciaBemPatrimonial
        fields = [
            "id",
            "numero_ntbpm",
            "numero_processo",
            "observacao",
            "unidade_orcamentaria_origem",
            "unidade_orcamentaria_destino",
            "unidade_administrativa_destino",
            "criado_por",
            "criado_em",
            "atualizado_em",
            "total_itens",
            "url_documento_ntbpm",
        ]
        read_only_fields = fields

    def get_total_itens(self, obj: TransferenciaBemPatrimonial) -> int:
        return obj.itens.count()

    def get_nome_bem(self, obj: TransferenciaBemPatrimonial) -> str:
        return ", ".join(item.bem.nome for item in obj.itens.all())

    def get_url_documento_ntbpm(self, obj: TransferenciaBemPatrimonial):
        if not obj.numero_ntbpm:
            return None

        request = self.context.get("request")
        if not request:
            return None

        try:
            path = reverse("transferencias-documento-ntbpm", kwargs={"pk": obj.pk})
            return request.build_absolute_uri(path)
        except Exception:
            return None


class TransferenciaBemPatrimonialListSerializer(
    TransferenciaBemPatrimonialBaseSerializer
):
    nome_bem = serializers.SerializerMethodField()

    class Meta(TransferenciaBemPatrimonialBaseSerializer.Meta):
        fields = [
            "id",
            "nome_bem",
            "numero_ntbpm",
            "numero_processo",
            "unidade_orcamentaria_origem",
            "unidade_orcamentaria_destino",
            "criado_por",
            "criado_em",
            "atualizado_em",
            "total_itens",
            "url_documento_ntbpm",
        ]


class TransferenciaBemPatrimonialDetailSerializer(
    TransferenciaBemPatrimonialBaseSerializer
):
    itens = TransferenciaBensItemSimpleSerializer(many=True, read_only=True)

    class Meta(TransferenciaBemPatrimonialBaseSerializer.Meta):
        fields = TransferenciaBemPatrimonialBaseSerializer.Meta.fields + ["itens"]


class TransferenciaBemPatrimonialCreateSerializer(serializers.ModelSerializer):
    itens = TransferenciaBensItemCreateSerializer(many=True)
    unidade_orcamentaria_destino = serializers.PrimaryKeyRelatedField(
        queryset=queryset_uos_destino_externas()
    )

    class Meta:
        model = TransferenciaBemPatrimonial
        fields = [
            "unidade_orcamentaria_destino",
            "numero_processo",
            "observacao",
            "itens",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")
        user = getattr(request, "user", None)
        uo_origem = obter_uo_referencia_do_usuario(user)

        self.fields["unidade_orcamentaria_destino"].queryset = queryset_uos_destino_externas(
            getattr(uo_origem, "pk", None)
        )

    def validate_itens(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not value:
            raise serializers.ValidationError("É necessário informar ao menos um bem.")

        bem_ids = [item["bem"].pk for item in value]
        if len(set(bem_ids)) != len(bem_ids):
            raise serializers.ValidationError(
                "Não é permitido repetir o mesmo bem na transferência."
            )
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Usuário autenticado é obrigatório.")

        uo_origem = obter_uo_referencia_do_usuario(user)
        if not uo_origem:
            raise serializers.ValidationError(
                {
                    "unidade_orcamentaria_origem": (
                        "Não foi possível identificar a UO de origem do usuário."
                    )
                }
            )

        uo_destino = attrs.get("unidade_orcamentaria_destino")
        if not uo_destino:
            raise serializers.ValidationError(
                {
                    "unidade_orcamentaria_destino": (
                        "Unidade Orçamentária de destino é obrigatória."
                    )
                }
            )

        if not unidade_orcamentaria_eh_externa(uo_destino):
            raise serializers.ValidationError(
                {
                    "unidade_orcamentaria_destino": (
                        "A Unidade Orçamentária de destino deve ser externa à SME."
                    )
                }
            )

        if uo_destino.pk == uo_origem.pk:
            raise serializers.ValidationError(
                {
                    "unidade_orcamentaria_destino": (
                        "A Unidade Orçamentária de destino deve ser diferente da UO de origem."
                    )
                }
            )

        ua_destino = obter_ua_ponto_central(uo_destino)
        if not ua_destino:
            raise serializers.ValidationError(
                {
                    "unidade_orcamentaria_destino": MENSAGEM_SEM_PONTO_CENTRAL,
                }
            )

        self._validar_bens(uo_origem, attrs["itens"])

        attrs["unidade_orcamentaria_origem"] = uo_origem
        attrs["unidade_administrativa_destino"] = ua_destino
        return attrs

    def _validar_bens(self, uo_origem, itens):
        erros = {}
        for idx, item in enumerate(itens):
            bem = item["bem"]

            if bem.unidade_administrativa_id is None:
                erros[str(idx)] = {
                    "bem": (
                        f"O bem '{bem.numero_patrimonial}' não possui unidade administrativa."
                    )
                }
                continue

            if bem.unidade_administrativa.unidade_orcamentaria_id != uo_origem.id:
                erros[str(idx)] = {
                    "bem": (
                        f"O bem '{bem.numero_patrimonial}' não pertence à UO de origem da transferência."
                    )
                }
                continue

            if bem.status != constants.APROVADO:
                erros[str(idx)] = {
                    "bem": (
                        f"O bem '{bem.numero_patrimonial}' precisa estar com status 'Aprovado' para ser transferido."
                    )
                }
                continue

            if getattr(bem, "bloqueado_conciliacao", False):
                erros[str(idx)] = {
                    "bem": (
                        f"O bem '{bem.numero_patrimonial}' está bloqueado por inventário e não pode ser movimentado."
                    )
                }
                continue

            if getattr(bem, "tem_movimentacao_pendente", False):
                erros[str(idx)] = {
                    "bem": (
                        f"O bem '{bem.numero_patrimonial}' já possui uma movimentação pendente."
                    )
                }

        if erros:
            raise serializers.ValidationError({"itens": erros})

    @transaction.atomic
    def create(self, validated_data):
        itens = validated_data.pop("itens")
        user = self.context["request"].user

        transferencia = TransferenciaBemPatrimonial.objects.create(
            **validated_data,
            criado_por=user,
        )

        for item in itens:
            TransferenciaBensItem.objects.create(
                transferencia=transferencia,
                bem=item["bem"],
            )

        with audit_as(user):
            transferencia.efetivar_transferencia(user)
        transferencia.refresh_from_db()
        return transferencia
