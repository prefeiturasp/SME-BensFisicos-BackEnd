from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from dados_comuns.escopo import filtrar_ua_origem_por_escopo
from dados_comuns.models import UnidadeAdministrativa

from inventario import constants
from inventario.models import (
    ConciliacaoUA,
    ItemConciliacao,
    OcorrenciaConciliacao,
    ParametroConciliacaoAnual,
)


class ParametroConciliacaoAnualListSerializer(serializers.ModelSerializer):
    unidade_orcamentaria_codigo = serializers.CharField(
        source="unidade_orcamentaria.codigo",
        read_only=True,
    )
    unidade_orcamentaria_nome = serializers.CharField(
        source="unidade_orcamentaria.nome",
        read_only=True,
    )
    unidade_orcamentaria_sigla = serializers.CharField(
        source="unidade_orcamentaria.sigla",
        read_only=True,
    )
    esta_vigente = serializers.BooleanField(read_only=True)

    class Meta:
        model = ParametroConciliacaoAnual
        fields = [
            "id",
            "unidade_orcamentaria",
            "unidade_orcamentaria_codigo",
            "unidade_orcamentaria_nome",
            "unidade_orcamentaria_sigla",
            "ano_referencia",
            "periodo_inicial",
            "periodo_final",
            "ativo",
            "esta_vigente",
        ]
        read_only_fields = fields


class ParametroConciliacaoAnualDetailSerializer(
    ParametroConciliacaoAnualListSerializer
):
    class Meta(ParametroConciliacaoAnualListSerializer.Meta):
        read_only_fields = ["id", "esta_vigente"]


def _resumo_situacoes(conciliacao):
    situacoes = [
        ("encontrados", constants.ENCONTRADO_SEM_DIVERGENCIA),
        ("nao_encontrados", constants.NAO_ENCONTRADO),
        ("divergentes", constants.DIVERGENTE),
        ("em_processo_baixa", constants.EM_PROCESSO_BAIXA_FISICA),
        ("baixa_fisica", constants.BAIXA_FISICA),
        ("encontrados_com_divergencia", constants.ENCONTRADO),
    ]
    return {
        chave: conciliacao.itens.filter(situacao=valor).count()
        for chave, valor in situacoes
    }


class ConciliacaoUACreateSerializer(serializers.ModelSerializer):
    """
    Serializer de criação de Conciliação.

    Replica as regras do ConciliacaoUAAdminForm:
    - tipo é forçado para EVENTUAL (anuais são criadas automaticamente pelo sistema).
    - unidade_administrativa é validada contra o escopo do usuário.
    - Bloqueia criação quando já existe conciliação em aberto para a UA.
    - periodo_final é obrigatório para EVENTUAL.
    """

    class Meta:
        model = ConciliacaoUA
        fields = ["unidade_administrativa", "tipo", "periodo_final"]
        extra_kwargs = {
            "unidade_administrativa": {"required": True, "allow_null": False},
            "tipo": {"required": False},
            "periodo_final": {"required": False, "allow_null": True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if "unidade_administrativa" in self.fields and user is not None:
            base_qs = UnidadeAdministrativa.objects.filter(
                status=UnidadeAdministrativa.ATIVA
            )
            self.fields["unidade_administrativa"].queryset = (
                filtrar_ua_origem_por_escopo(user, base_qs)
            )

    def validate_tipo(self, value):
        if value is None:
            return constants.CONCILIACAO_EVENTUAL
        if value != constants.CONCILIACAO_EVENTUAL:
            raise serializers.ValidationError(
                "Conciliações anuais são criadas automaticamente pelo sistema. "
                "Para criar uma conciliação manualmente, use o tipo 'eventual'."
            )
        return value

    def validate(self, attrs):
        attrs.setdefault("tipo", constants.CONCILIACAO_EVENTUAL)
        attrs["tipo"] = self.validate_tipo(attrs.get("tipo"))

        unidade_administrativa = attrs.get("unidade_administrativa")
        if unidade_administrativa is None:
            raise serializers.ValidationError(
                {"unidade_administrativa": "Unidade Administrativa é obrigatória."}
            )

        request = self.context.get("request")
        user = getattr(request, "user", None)
        self._validar_ua_no_escopo(user, unidade_administrativa)
        self._validar_sem_conciliacao_aberta(unidade_administrativa)

        tipo = attrs["tipo"]
        periodo_final = attrs.get("periodo_final")

        if tipo == constants.CONCILIACAO_EVENTUAL and not periodo_final:
            raise serializers.ValidationError(
                {"periodo_final": "Este campo é obrigatório para conciliação eventual."}
            )

        return attrs

    def _validar_ua_no_escopo(self, user, unidade_administrativa):
        if user is None:
            return
        allowed_qs = filtrar_ua_origem_por_escopo(
            user,
            UnidadeAdministrativa.objects.filter(status=UnidadeAdministrativa.ATIVA),
        )
        if not allowed_qs.filter(pk=unidade_administrativa.pk).exists():
            raise serializers.ValidationError(
                {
                    "unidade_administrativa": (
                        "Você não tem permissão para usar esta Unidade Administrativa."
                    )
                }
            )

    def _validar_sem_conciliacao_aberta(self, unidade_administrativa):
        if self.instance and self.instance.pk:
            return
        existe_aberto = ConciliacaoUA.objects.filter(
            unidade_administrativa=unidade_administrativa,
            status=constants.CONCILIACAO_EM_ABERTO,
        ).exists()
        if existe_aberto:
            raise serializers.ValidationError(
                {
                    "unidade_administrativa": (
                        "Já existe uma conciliação em aberto para esta Unidade "
                        "Administrativa. Feche a conciliação anterior para abrir uma nova."
                    )
                }
            )

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        conciliacao = ConciliacaoUA(**validated_data)
        if user is not None:
            conciliacao.criado_por = user
        try:
            conciliacao.save()
        except DjangoValidationError as exc:
            self._raise_drf_validation_error(exc)
        return conciliacao

    def _raise_drf_validation_error(self, exc):
        if hasattr(exc, "message_dict"):
            errors = dict(exc.message_dict)
            if "__all__" in errors:
                errors["non_field_errors"] = errors.pop("__all__")
            raise serializers.ValidationError(errors)
        if hasattr(exc, "messages"):
            raise serializers.ValidationError({"non_field_errors": exc.messages})
        raise serializers.ValidationError({"non_field_errors": [str(exc)]})


class ConciliacaoUAListSerializer(serializers.ModelSerializer):
    unidade_administrativa_codigo = serializers.CharField(
        source="unidade_administrativa.codigo",
        read_only=True,
    )
    unidade_administrativa_nome = serializers.CharField(
        source="unidade_administrativa.nome",
        read_only=True,
    )
    unidade_administrativa_sigla = serializers.CharField(
        source="unidade_administrativa.sigla",
        read_only=True,
    )
    unidade_orcamentaria_codigo = serializers.CharField(
        source="unidade_administrativa.unidade_orcamentaria.codigo",
        read_only=True,
        default="",
    )
    unidade_orcamentaria_nome = serializers.CharField(
        source="unidade_administrativa.unidade_orcamentaria.nome",
        read_only=True,
        default="",
    )
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    total_itens = serializers.SerializerMethodField()
    resumo_situacoes = serializers.SerializerMethodField()
    ano_vigencia = serializers.SerializerMethodField()

    class Meta:
        model = ConciliacaoUA
        fields = [
            "id",
            "numero_conciliacao",
            "unidade_administrativa",
            "unidade_administrativa_codigo",
            "unidade_administrativa_nome",
            "unidade_administrativa_sigla",
            "unidade_orcamentaria_codigo",
            "unidade_orcamentaria_nome",
            "tipo",
            "tipo_display",
            "periodo_final",
            "status",
            "status_display",
            "total_itens",
            "resumo_situacoes",
            "ano_vigencia",
            "criado_em",
            "fechado_em",
        ]
        read_only_fields = fields

    def get_total_itens(self, obj):
        return obj.itens.count()

    def get_resumo_situacoes(self, obj):
        return _resumo_situacoes(obj)

    def get_ano_vigencia(self, obj):
        if obj.periodo_final:
            return obj.periodo_final.year
        return None


class ConciliacaoUADetailSerializer(ConciliacaoUAListSerializer):
    criado_por_nome = serializers.CharField(
        source="criado_por.nome", read_only=True, default=""
    )
    criado_por_rf = serializers.CharField(
        source="criado_por.rf", read_only=True, default=""
    )
    fechado_por_nome = serializers.CharField(
        source="fechado_por.nome", read_only=True, default=""
    )
    fechado_por_rf = serializers.CharField(
        source="fechado_por.rf", read_only=True, default=""
    )
    esta_aberto = serializers.BooleanField(read_only=True)

    class Meta(ConciliacaoUAListSerializer.Meta):
        fields = ConciliacaoUAListSerializer.Meta.fields + [
            "criado_por",
            "criado_por_nome",
            "criado_por_rf",
            "criado_em",
            "fechado_por",
            "fechado_por_nome",
            "fechado_por_rf",
            "fechado_em",
            "esta_aberto",
        ]
        read_only_fields = fields


class BemPatrimonialSimplificadoSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    numero_patrimonial = serializers.CharField(read_only=True)
    nome = serializers.CharField(read_only=True)
    descricao = serializers.CharField(read_only=True)
    marca = serializers.CharField(read_only=True)
    modelo = serializers.CharField(read_only=True)
    valor_unitario = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True
    )
    status = serializers.CharField(read_only=True)
    localizacao = serializers.CharField(read_only=True)
    bloqueado_conciliacao = serializers.BooleanField(read_only=True)


class OcorrenciaConciliacaoSerializer(serializers.ModelSerializer):
    situacao_display = serializers.CharField(
        source="get_situacao_display", read_only=True
    )
    registrado_por_nome = serializers.CharField(
        source="registrado_por.nome", read_only=True, default=""
    )
    registrado_por_rf = serializers.CharField(
        source="registrado_por.rf", read_only=True, default=""
    )

    class Meta:
        model = OcorrenciaConciliacao
        fields = [
            "id",
            "situacao",
            "situacao_display",
            "observacao",
            "divergencia",
            "registrado_por",
            "registrado_por_nome",
            "registrado_por_rf",
            "registrado_em",
        ]
        read_only_fields = fields


class ItemConciliacaoListSerializer(serializers.ModelSerializer):
    bem = BemPatrimonialSimplificadoSerializer(read_only=True)
    situacao_display = serializers.CharField(
        source="get_situacao_display", read_only=True
    )
    conciliacao_numero = serializers.CharField(
        source="conciliacao.numero_conciliacao", read_only=True
    )
    conciliacao_status = serializers.CharField(
        source="conciliacao.status", read_only=True
    )
    unidade_administrativa = serializers.IntegerField(
        source="conciliacao.unidade_administrativa_id", read_only=True
    )
    unidade_administrativa_sigla = serializers.CharField(
        source="conciliacao.unidade_administrativa.sigla", read_only=True
    )
    atualizado_por_nome = serializers.CharField(
        source="atualizado_por.nome", read_only=True, default=""
    )
    tem_ocorrencia = serializers.BooleanField(read_only=True)
    permite_registrar_ocorrencia = serializers.BooleanField(read_only=True)

    class Meta:
        model = ItemConciliacao
        fields = [
            "id",
            "conciliacao",
            "conciliacao_numero",
            "conciliacao_status",
            "unidade_administrativa",
            "unidade_administrativa_sigla",
            "bem",
            "situacao",
            "situacao_display",
            "observacao",
            "divergencia",
            "tem_ocorrencia",
            "permite_registrar_ocorrencia",
            "atualizado_por",
            "atualizado_por_nome",
            "atualizado_em",
        ]
        read_only_fields = fields


class ItemConciliacaoDetailSerializer(ItemConciliacaoListSerializer):
    ocorrencias = OcorrenciaConciliacaoSerializer(many=True, read_only=True)
    pode_marcar_como_encontrado = serializers.BooleanField(read_only=True)
    pode_resolver_situacao = serializers.BooleanField(read_only=True)
    conciliacao_esta_aberto = serializers.BooleanField(
        source="conciliacao.esta_aberto", read_only=True
    )

    class Meta(ItemConciliacaoListSerializer.Meta):
        fields = ItemConciliacaoListSerializer.Meta.fields + [
            "pode_marcar_como_encontrado",
            "pode_resolver_situacao",
            "conciliacao_esta_aberto",
            "ocorrencias",
        ]
        read_only_fields = fields


class RegistrarOcorrenciaSerializer(serializers.Serializer):
    situacao = serializers.ChoiceField(choices=constants.SITUACOES_ITEM_CONCILIACAO)
    observacao = serializers.CharField(required=False, allow_blank=True, default="")
    divergencia = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        situacao = attrs.get("situacao")
        divergencia = attrs.get("divergencia", "")
        if situacao == constants.DIVERGENTE and not divergencia:
            raise serializers.ValidationError(
                {"divergencia": "Campo divergência é obrigatório quando situação é Divergente."}
            )
        return attrs


class ConciliacaoHistoricoAcaoSerializer(serializers.Serializer):
    campo = serializers.CharField()
    valor_antigo = serializers.CharField(allow_null=True)
    valor_novo = serializers.CharField(allow_null=True)
    justificativa = serializers.CharField(allow_null=True, required=False)


class ConciliacaoHistoricoGrupoSerializer(serializers.Serializer):
    alterado_em = serializers.DateTimeField()
    alterado_por = serializers.IntegerField(allow_null=True)
    alterado_por_nome = serializers.CharField(allow_null=True)
    acoes = ConciliacaoHistoricoAcaoSerializer(many=True)


class ConciliacaoExportQuerySerializer(serializers.Serializer):
    formato = serializers.ChoiceField(choices=["pdf"])
