from collections import defaultdict

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.db.models import Q
from rest_framework import serializers

from bem_patrimonial import constants
from bem_patrimonial.models import (
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
    MovimentacaoBensItem,
)
from bem_patrimonial.serializers.historico_serializers import HistoricoGrupoSerializer
from dados_comuns.escopo import filtrar_ua_origem_por_escopo
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria

User = get_user_model()


CODIGO_UA_PONTO_CENTRAL = "001"
MENSAGEM_SEM_PONTO_CENTRAL = (
    "Não há ponto central cadastrado na Unidade Orçamentária de destino. "
    "Por favor, entrar em contato com o gestor."
)


def obter_uo_referencia_do_usuario(usuario):
    if not usuario:
        return None

    unidade_orcamentaria = getattr(usuario, "unidade_orcamentaria", None)
    if unidade_orcamentaria:
        return unidade_orcamentaria

    unidade_administrativa = getattr(usuario, "unidade_administrativa", None)
    return getattr(unidade_administrativa, "unidade_orcamentaria", None)


def queryset_uos_destino():
    return UnidadeOrcamentaria.objects.filter(ativa=True).order_by("codigo", "nome")


def queryset_uas_ativas():
    return (
        UnidadeAdministrativa.objects.filter(status=UnidadeAdministrativa.ATIVA)
        .select_related("unidade_orcamentaria")
        .order_by("unidade_orcamentaria__codigo", "codigo", "sigla", "nome")
    )


def queryset_uas_da_uo(unidade_orcamentaria):
    qs = queryset_uas_ativas()
    if not unidade_orcamentaria:
        return qs.none()
    return qs.filter(unidade_orcamentaria=unidade_orcamentaria)


def obter_ua_ponto_central(unidade_orcamentaria):
    if not unidade_orcamentaria:
        return None

    return (
        queryset_uas_da_uo(unidade_orcamentaria)
        .filter(
            Q(codigo=CODIGO_UA_PONTO_CENTRAL)
            | Q(codigo__endswith=f".{CODIGO_UA_PONTO_CENTRAL}")
        )
        .order_by("id")
        .first()
    )


class UnidadeOrcamentariaSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnidadeOrcamentaria
        fields = ["id", "codigo", "sigla", "nome", "ativa"]
        read_only_fields = fields


class MovimentacaoUoCadastroOptionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    codigo = serializers.CharField()
    nome = serializers.CharField()
    label = serializers.CharField()
    tem_ponto_central = serializers.BooleanField()


class UnidadeAdministrativaSimpleSerializer(serializers.ModelSerializer):
    unidade_orcamentaria = UnidadeOrcamentariaSimpleSerializer(read_only=True)

    class Meta:
        model = UnidadeAdministrativa
        fields = ["id", "codigo", "sigla", "nome", "status", "unidade_orcamentaria"]
        read_only_fields = fields


class UserSimpleSerializer(serializers.ModelSerializer):
    nome_completo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "nome_completo", "email"]
        read_only_fields = fields

    def get_nome_completo(self, obj):
        return obj.get_full_name() or getattr(obj, "nome", None) or obj.username


class BemPatrimonialSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = BemPatrimonial
        fields = ["id", "numero_patrimonial", "nome", "status"]
        read_only_fields = fields


class MovimentacaoBensItemSimpleSerializer(serializers.ModelSerializer):
    bem = BemPatrimonialSimpleSerializer(read_only=True)

    class Meta:
        model = MovimentacaoBensItem
        fields = ["id", "bem"]
        read_only_fields = fields


class MovimentacaoBensItemCreateSerializer(serializers.Serializer):
    bem = serializers.PrimaryKeyRelatedField(
        queryset=BemPatrimonial.objects.select_related("unidade_administrativa")
    )


class MovimentacaoBemPatrimonialBaseSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    unidade_administrativa_origem = UnidadeAdministrativaSimpleSerializer(read_only=True)
    unidade_administrativa_destino = UnidadeAdministrativaSimpleSerializer(read_only=True)
    unidade_orcamentaria_origem = UnidadeOrcamentariaSimpleSerializer(
        source="unidade_administrativa_origem.unidade_orcamentaria",
        read_only=True,
    )
    unidade_orcamentaria_destino = UnidadeOrcamentariaSimpleSerializer(
        source="unidade_administrativa_destino.unidade_orcamentaria",
        read_only=True,
    )
    solicitado_por = UserSimpleSerializer(read_only=True)
    aprovado_por = UserSimpleSerializer(read_only=True)
    rejeitado_por = UserSimpleSerializer(read_only=True)
    cancelado_por = UserSimpleSerializer(read_only=True)
    total_itens = serializers.SerializerMethodField()

    class Meta:
        model = MovimentacaoBemPatrimonial
        fields = [
            "id",
            "status",
            "status_display",
            "numero_cimbpm",
            "observacao",
            "unidade_administrativa_origem",
            "unidade_orcamentaria_origem",
            "unidade_administrativa_destino",
            "unidade_orcamentaria_destino",
            "solicitado_por",
            "aprovado_por",
            "rejeitado_por",
            "cancelado_por",
            "criado_em",
            "atualizado_em",
            "total_itens",
        ]
        read_only_fields = fields

    def get_total_itens(self, obj):
        return obj.itens.count()

    def _build_url(self, viewname, pk):
        request = self.context.get("request")
        if not request:
            return None
        try:
            return request.build_absolute_uri(reverse(viewname, kwargs={"pk": pk}))
        except Exception:
            return None


class MovimentacaoBemPatrimonialListSerializer(
    MovimentacaoBemPatrimonialBaseSerializer
):
    itens = MovimentacaoBensItemSimpleSerializer(many=True, read_only=True)

    class Meta(MovimentacaoBemPatrimonialBaseSerializer.Meta):
        fields = MovimentacaoBemPatrimonialBaseSerializer.Meta.fields + ["itens"]


class MovimentacaoBemPatrimonialDetailSerializer(
    MovimentacaoBemPatrimonialBaseSerializer
):
    itens = MovimentacaoBensItemSimpleSerializer(many=True, read_only=True)
    url_aprovar = serializers.SerializerMethodField()
    url_rejeitar = serializers.SerializerMethodField()
    url_cancelar = serializers.SerializerMethodField()
    url_historico = serializers.SerializerMethodField()
    url_documento_cimbpm = serializers.SerializerMethodField()

    class Meta(MovimentacaoBemPatrimonialBaseSerializer.Meta):
        fields = (
            MovimentacaoBemPatrimonialBaseSerializer.Meta.fields
            + [
                "itens",
                "url_aprovar",
                "url_rejeitar",
                "url_cancelar",
                "url_historico",
                "url_documento_cimbpm",
            ]
        )

    def get_url_aprovar(self, obj):
        if obj.status == constants.ENVIADA:
            return self._build_url("movimentacoes-aprovar", obj.pk)
        return None

    def get_url_rejeitar(self, obj):
        if obj.status == constants.ENVIADA:
            return self._build_url("movimentacoes-rejeitar", obj.pk)
        return None

    def get_url_cancelar(self, obj):
        if obj.status == constants.ENVIADA:
            return self._build_url("movimentacoes-cancelar", obj.pk)
        return None

    def get_url_historico(self, obj):
        return self._build_url("movimentacoes-historico", obj.pk)

    def get_url_documento_cimbpm(self, obj):
        if obj.numero_cimbpm:
            return self._build_url("movimentacoes-documento-cimbpm", obj.pk)
        return None


class MovimentacaoBemPatrimonialCreateSerializer(serializers.ModelSerializer):
    itens = MovimentacaoBensItemCreateSerializer(many=True)
    unidade_orcamentaria_destino = serializers.PrimaryKeyRelatedField(
        queryset=queryset_uos_destino(), required=False
    )
    unidade_administrativa_destino = serializers.PrimaryKeyRelatedField(
        queryset=queryset_uas_ativas(), required=False
    )

    class Meta:
        model = MovimentacaoBemPatrimonial
        fields = [
            "unidade_administrativa_origem",
            "unidade_orcamentaria_destino",
            "unidade_administrativa_destino",
            "observacao",
            "itens",
        ]

    def validate_itens(self, value):
        if not value:
            raise serializers.ValidationError("Adicione ao menos um bem na movimentação.")
        bem_ids = [item["bem"].pk for item in value]
        if len(set(bem_ids)) != len(bem_ids):
            raise serializers.ValidationError("Não é permitido repetir o mesmo bem na movimentação.")
        return value

    def validate_unidade_administrativa_origem(self, value):
        if not value:
            raise serializers.ValidationError("Unidade administrativa de origem é obrigatória.")
        if value.status != UnidadeAdministrativa.ATIVA:
            raise serializers.ValidationError("A unidade de origem está inativa.")

        user = self.context["request"].user
        if getattr(user, "is_superuser", False):
            return value

        qs_permitidas = filtrar_ua_origem_por_escopo(user, queryset_uas_ativas())
        if not qs_permitidas.filter(pk=value.pk).exists():
            raise serializers.ValidationError("UA de origem fora do seu escopo de acesso.")
        return value

    def _validar_bens(self, ua_origem, itens):
        erros = {}
        for idx, item in enumerate(itens):
            bem = item["bem"]
            if bem.unidade_administrativa_id != ua_origem.id:
                erros[str(idx)] = {
                    "bem": "O bem selecionado não pertence à unidade administrativa de origem."
                }
                continue
            if bem.status != constants.APROVADO:
                erros[str(idx)] = {
                    "bem": (
                        f"O bem '{bem.numero_patrimonial}' precisa estar com status 'Aprovado' "
                        "para ser movimentado."
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

    def _resolver_destino(self, attrs):
        user = self.context["request"].user
        ua_origem = attrs["unidade_administrativa_origem"]

        uo_referencia = obter_uo_referencia_do_usuario(user) or ua_origem.unidade_orcamentaria
        uo_destino = attrs.get("unidade_orcamentaria_destino") or uo_referencia
        if not uo_destino:
            raise serializers.ValidationError(
                {"unidade_orcamentaria_destino": "Unidade Orçamentária de destino é obrigatória."}
            )
        if not getattr(uo_destino, "ativa", False):
            raise serializers.ValidationError(
                {"unidade_orcamentaria_destino": "Unidade Orçamentária de destino está inativa."}
            )

        destino_mesma_uo = uo_destino.pk == uo_referencia.pk if uo_referencia else False
        ua_destino = attrs.get("unidade_administrativa_destino")

        if destino_mesma_uo:
            if not ua_destino:
                raise serializers.ValidationError(
                    {"unidade_administrativa_destino": "Unidade administrativa de destino é obrigatória."}
                )
            if ua_destino.unidade_orcamentaria_id != uo_destino.id:
                raise serializers.ValidationError(
                    {
                        "unidade_administrativa_destino": (
                            "A Unidade Administrativa de destino não pertence à Unidade Orçamentária selecionada."
                        )
                    }
                )
        else:
            ua_destino = obter_ua_ponto_central(uo_destino)
            if not ua_destino:
                raise serializers.ValidationError(
                    {"unidade_orcamentaria_destino": MENSAGEM_SEM_PONTO_CENTRAL}
                )

        if ua_destino.id == ua_origem.id:
            raise serializers.ValidationError(
                "Operação não permitida: origem e destino são iguais."
            )

        attrs["unidade_orcamentaria_destino"] = uo_destino
        attrs["unidade_administrativa_destino"] = ua_destino

    def validate(self, attrs):
        self._resolver_destino(attrs)
        self._validar_bens(attrs["unidade_administrativa_origem"], attrs["itens"])
        return attrs

    def create(self, validated_data):
        itens = validated_data.pop("itens")
        validated_data.pop("unidade_orcamentaria_destino", None)
        user = self.context["request"].user
        bem_patrimonial = itens[0]["bem"]

        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            **validated_data,
            bem_patrimonial=bem_patrimonial,
            solicitado_por=user,
            status=constants.ENVIADA,
        )

        for item in itens:
            MovimentacaoBensItem.objects.create(
                movimentacao=movimentacao,
                bem=item["bem"],
            )

        return movimentacao


class MovimentacaoBemPatrimonialUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimentacaoBemPatrimonial
        fields = ["observacao"]

    def validate(self, attrs):
        if set(self.initial_data.keys()) - {"observacao"}:
            raise serializers.ValidationError(
                {"detail": "Nesta versão da API, apenas observação pode ser alterada."}
            )

        if self.instance.status != constants.ENVIADA:
            raise serializers.ValidationError(
                "Apenas movimentações com status 'Enviada' podem ser editadas."
            )

        request = self.context.get("request")
        user = getattr(request, "user", None)
        if (
            user
            and getattr(user, "is_operador_inventario", False)
            and not getattr(user, "is_gestor_patrimonio", False)
            and self.instance.solicitado_por_id != user.id
        ):
            raise serializers.ValidationError(
                "Não é permitido alterar uma movimentação solicitada por outro usuário."
            )

        return attrs


class MovimentacaoHistoricoAcaoSerializer(serializers.Serializer):
    campo = serializers.CharField()
    valor_antigo = serializers.CharField(allow_null=True)
    valor_novo = serializers.CharField(allow_null=True)
    justificativa = serializers.CharField(allow_null=True, required=False)


class MovimentacaoHistoricoGrupoSerializer(serializers.Serializer):
    alterado_em = serializers.DateTimeField()
    alterado_por = serializers.IntegerField(allow_null=True)
    alterado_por_nome = serializers.CharField(allow_null=True)
    acoes = MovimentacaoHistoricoAcaoSerializer(many=True)
