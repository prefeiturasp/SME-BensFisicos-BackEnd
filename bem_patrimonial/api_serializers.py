from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse
from django.db import transaction
from typing import Dict, Any

from .models import BaixaFisicaBemPatrimonial, BaixaFisicaBensItem, BemPatrimonial, NBBPM
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.escopo import filtrar_ua_origem_por_escopo, filtrar_queryset_por_escopo
from . import constants

User = get_user_model()

_STATUS_BEM_INVALIDOS_PARA_BAIXA = {
    constants.BAIXA_FISICA_AGUARDANDO_APROVACAO,
    constants.BLOQUEADO,
    *constants.STATUS_FINAIS_BEM,
}


def _resolver_numero_nbbpm(obj) -> str:
    """Retorna número da NBBPM consolidada (M2M) com fallback no legado Baixa.numero_nbbpm."""
    try:
        if hasattr(obj, '_prefetched_objects_cache') and 'nbbpms_lote' in obj._prefetched_objects_cache:
            lotes = obj._prefetched_objects_cache['nbbpms_lote']
            nbbpm = lotes[0] if lotes else None
        else:
            nbbpm = obj.nbbpms_lote.first()
        if nbbpm and nbbpm.numero:
            return nbbpm.numero
    except Exception:
        pass
    return obj.numero_nbbpm or ""


# ============================================================================
# SERIALIZERS DE MODELOS RELACIONADOS
# ============================================================================

class UnidadeAdministrativaSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnidadeAdministrativa
        fields = ['id', 'nome', 'sigla', 'codigo', 'status']
        read_only_fields = fields


class UserSimpleSerializer(serializers.ModelSerializer):
    nome_completo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'nome_completo', 'email']
        read_only_fields = fields

    def get_nome_completo(self, obj: User) -> str:
        return obj.get_full_name() or obj.username


class BemPatrimonialSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = BemPatrimonial
        fields = ['id', 'numero_patrimonial', 'nome', 'descricao', 'status']
        read_only_fields = fields


# ============================================================================
# SERIALIZERS DE BAIXA FÍSICA ITEM
# ============================================================================

class BaixaFisicaBensItemSerializer(serializers.ModelSerializer):
    bem = BemPatrimonialSimpleSerializer(read_only=True)

    class Meta:
        model = BaixaFisicaBensItem
        fields = ['id', 'bem']
        read_only_fields = fields


class BaixaFisicaBensItemCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BaixaFisicaBensItem
        fields = ['id', 'bem']

    def validate_bem(self, value: BemPatrimonial) -> BemPatrimonial:
        if not value:
            raise serializers.ValidationError("Bem patrimonial é obrigatório.")

        if value.status in _STATUS_BEM_INVALIDOS_PARA_BAIXA:
            baixa_id = self.context.get('baixa_id')

            if value.status == constants.BAIXA_FISICA_AGUARDANDO_APROVACAO:
                item_atual = BaixaFisicaBensItem.objects.filter(
                    bem=value,
                    baixa__status__in=[constants.AGUARDANDO_ENVIO, constants.SOLICITADA]
                ).exclude(baixa_id=baixa_id).first()

                if item_atual:
                    raise serializers.ValidationError(
                        f"Este bem já está incluído em outra baixa física "
                        f"(Baixa #{item_atual.baixa.id})."
                    )
            else:
                raise serializers.ValidationError(
                    f"O bem '{value.numero_patrimonial}' possui status "
                    f"'{value.get_status_display()}' e não pode ser incluído em uma baixa física."
                )

        return value


# ============================================================================
# SERIALIZERS DE BAIXA FÍSICA — LEITURA
# ============================================================================

class BaixaFisicaBemPatrimonialListSerializer(serializers.ModelSerializer):
    unidade_administrativa_origem = UnidadeAdministrativaSimpleSerializer(read_only=True)
    criado_por = UserSimpleSerializer(read_only=True)
    aprovado_por = UserSimpleSerializer(read_only=True)
    status_display = serializers.SerializerMethodField()
    total_itens = serializers.SerializerMethodField()
    numero_nbbpm = serializers.SerializerMethodField()

    class Meta:
        model = BaixaFisicaBemPatrimonial
        fields = [
            'id',
            'numero_processo_baixa',
            'numero_nbbpm',
            'unidade_administrativa_origem',
            'status',
            'status_display',
            'criado_por',
            'data_criacao',
            'aprovado_por',
            'data_aprovacao',
            'data_baixa',
            'total_itens',
        ]
        read_only_fields = fields

    def get_status_display(self, obj: BaixaFisicaBemPatrimonial) -> str:
        if obj.status == constants.AGUARDANDO_ENVIO:
            return "Em elaboração"
        return obj.get_status_display()

    def get_total_itens(self, obj: BaixaFisicaBemPatrimonial) -> int:
        return obj.itens.count()

    def get_numero_nbbpm(self, obj: BaixaFisicaBemPatrimonial) -> str:
        return _resolver_numero_nbbpm(obj)


class BaixaFisicaBemPatrimonialDetailSerializer(serializers.ModelSerializer):
    unidade_administrativa_origem = UnidadeAdministrativaSimpleSerializer(read_only=True)
    criado_por = UserSimpleSerializer(read_only=True)
    aprovado_por = UserSimpleSerializer(read_only=True)
    status_display = serializers.SerializerMethodField()
    itens = BaixaFisicaBensItemSerializer(many=True, read_only=True)
    numero_nbbpm = serializers.SerializerMethodField()

    url_solicitar = serializers.SerializerMethodField()
    url_aprovar = serializers.SerializerMethodField()
    url_recusar = serializers.SerializerMethodField()
    url_solicitar_correcao = serializers.SerializerMethodField()
    url_gerar_nbbpm = serializers.SerializerMethodField()
    url_gerar_laudo = serializers.SerializerMethodField()

    class Meta:
        model = BaixaFisicaBemPatrimonial
        fields = [
            'id',
            'numero_processo_baixa',
            'numero_nbbpm',
            'unidade_administrativa_origem',
            'status',
            'status_display',
            'criado_por',
            'data_criacao',
            'aprovado_por',
            'data_aprovacao',
            'data_baixa',
            'itens',
            'url_solicitar',
            'url_aprovar',
            'url_recusar',
            'url_solicitar_correcao',
            'url_gerar_nbbpm',
            'url_gerar_laudo',
        ]
        read_only_fields = fields

    def get_numero_nbbpm(self, obj: BaixaFisicaBemPatrimonial) -> str:
        return _resolver_numero_nbbpm(obj)

    def get_status_display(self, obj: BaixaFisicaBemPatrimonial) -> str:
        if obj.status == constants.AGUARDANDO_ENVIO:
            return "Em elaboração"
        return obj.get_status_display()

    def _build_url(self, viewname: str, pk: int) -> str | None:
        request = self.context.get('request')
        if not request:
            return None
        try:
            path = reverse(viewname, kwargs={'pk': pk})
            return request.build_absolute_uri(path)
        except Exception:
            return None

    def _usuario_e_gestor(self) -> bool:
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False
        user = request.user
        return user.is_gestor_patrimonio or user.is_superuser

    def get_url_solicitar(self, obj: BaixaFisicaBemPatrimonial):
        if obj.status == constants.AGUARDANDO_ENVIO:
            return self._build_url('baixas-fisicas-enviar-solicitacao', obj.id)
        return None

    def get_url_aprovar(self, obj: BaixaFisicaBemPatrimonial):
        if obj.status == constants.SOLICITADA and self._usuario_e_gestor():
            return self._build_url('baixas-fisicas-aprovar', obj.id)
        return None

    def get_url_recusar(self, obj: BaixaFisicaBemPatrimonial):
        if obj.status in [constants.AGUARDANDO_ENVIO, constants.SOLICITADA] and self._usuario_e_gestor():
            return self._build_url('baixas-fisicas-recusar', obj.id)
        return None

    def get_url_solicitar_correcao(self, obj: BaixaFisicaBemPatrimonial):
        if obj.status != constants.SOLICITADA:
            return None
        request = self.context.get('request')
        user = getattr(request, "user", None) if request else None
        is_criador = bool(user and getattr(obj, "criado_por_id", None) and getattr(user, "pk", None) == obj.criado_por_id)
        if self._usuario_e_gestor() or is_criador:
            return self._build_url('baixas-fisicas-solicitar-correcao', obj.id)
        return None

    def get_url_gerar_nbbpm(self, obj: BaixaFisicaBemPatrimonial):
        if obj.status != constants.ACEITA:
            return None
        try:
            if hasattr(obj, '_prefetched_objects_cache') and 'nbbpms_lote' in obj._prefetched_objects_cache:
                lotes = obj._prefetched_objects_cache['nbbpms_lote']
                nbbpm = lotes[0] if lotes else None
            else:
                nbbpm = obj.nbbpms_lote.first()
            if nbbpm:
                return self._build_url('nbbpm-pdf', nbbpm.id)
        except Exception:
            pass
        return None

    def get_url_gerar_laudo(self, obj: BaixaFisicaBemPatrimonial):
        if obj.status == constants.ACEITA:
            return self._build_url('baixas-fisicas-gerar-laudo', obj.id)
        return None


# ============================================================================
# SERIALIZERS DE CRIAÇÃO E ATUALIZAÇÃO
# ============================================================================

class BaixaFisicaBemPatrimonialCreateSerializer(serializers.ModelSerializer):
    itens = BaixaFisicaBensItemCreateSerializer(many=True)

    class Meta:
        model = BaixaFisicaBemPatrimonial
        fields = [
            # numero_processo_baixa e data_baixa agora são opcionais no novo fluxo
            'numero_processo_baixa',
            'unidade_administrativa_origem',
            'data_baixa',
            'itens',
        ]
        extra_kwargs = {
            'numero_processo_baixa': {'required': False, 'allow_blank': True, 'default': ''},
            'data_baixa': {'required': False, 'allow_null': True, 'default': None},
        }

    def validate_itens(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError(
                "É necessário informar ao menos um bem para a baixa física."
            )
        return value

    def validate_data_baixa(self, value):
        # data_baixa é opcional; valida apenas se informada
        if value and value > timezone.now().date():
            raise serializers.ValidationError(
                "A data de baixa não pode ser futura."
            )
        return value

    def validate_unidade_administrativa_origem(self, value: UnidadeAdministrativa) -> UnidadeAdministrativa:
        if not value:
            raise serializers.ValidationError(
                "Unidade administrativa de origem é obrigatória."
            )
        if value.status != UnidadeAdministrativa.ATIVA:
            raise serializers.ValidationError(
                "A unidade administrativa está inativa."
            )
        user = self.context['request'].user
        base_qs = UnidadeAdministrativa.objects.filter(
            status=UnidadeAdministrativa.ATIVA
        )
        uas_permitidas = filtrar_ua_origem_por_escopo(user, base_qs)
        if not uas_permitidas.filter(pk=value.pk).exists():
            raise serializers.ValidationError(
                "Você não tem permissão para criar uma baixa física para esta "
                "unidade administrativa."
            )
        return value

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        ua_origem = attrs.get('unidade_administrativa_origem')
        itens = attrs.get('itens', [])

        if ua_origem and itens:
            for item_data in itens:
                bem = item_data.get('bem')
                if bem and bem.unidade_administrativa != ua_origem:
                    raise serializers.ValidationError(
                        f"O bem '{bem.numero_patrimonial}' não pertence à unidade "
                        f"administrativa de origem selecionada."
                    )
        return attrs

    def _atualizar_status_bem(self, bem: BemPatrimonial, novo_status: str) -> None:
        bem.status = novo_status
        bem.save(update_fields=['status'])

    @transaction.atomic
    def create(self, validated_data: Dict[str, Any]) -> BaixaFisicaBemPatrimonial:
        itens_data = validated_data.pop('itens')
        user = self.context['request'].user

        baixa = BaixaFisicaBemPatrimonial.objects.create(
            **validated_data,
            criado_por=user,
            status=constants.AGUARDANDO_ENVIO,
        )

        for item_data in itens_data:
            BaixaFisicaBensItem.objects.create(baixa=baixa, **item_data)
            self._atualizar_status_bem(item_data['bem'], constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)

        return baixa


class BaixaFisicaBemPatrimonialUpdateSerializer(serializers.ModelSerializer):
    CAMPOS_EDITAVEIS = {'itens'}

    itens = serializers.ListField(child=serializers.DictField(), write_only=True)

    class Meta:
        model = BaixaFisicaBemPatrimonial
        fields = ['itens']

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        instance = self.instance
        campos_nao_permitidos = set(self.initial_data) - self.CAMPOS_EDITAVEIS
        if campos_nao_permitidos:
            raise serializers.ValidationError(
                {
                    campo: (
                        "Este campo não pode ser alterado após a criação da baixa física."
                    )
                    for campo in sorted(campos_nao_permitidos)
                }
            )
        if instance.status != constants.AGUARDANDO_ENVIO:
            raise serializers.ValidationError(
                "Apenas baixas com status 'Em elaboração' podem ser editadas."
            )
        return attrs

    def validate_itens(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError(
                "É necessário informar ao menos um bem para a baixa física."
            )

        baixa_id = self.instance.id if self.instance else None
        for item_data in value:
            s = BaixaFisicaBensItemCreateSerializer(
                data=item_data,
                context={'baixa_id': baixa_id}
            )
            if not s.is_valid():
                raise serializers.ValidationError(s.errors)

        return value

    def _restaurar_status_bem(self, bem: BemPatrimonial) -> None:
        if bem.status == constants.BAIXA_FISICA_AGUARDANDO_APROVACAO:
            bem.status = constants.APROVADO
            bem.save(update_fields=['status'])

    def _marcar_bem_em_baixa(self, bem: BemPatrimonial) -> None:
        bem.status = constants.BAIXA_FISICA_AGUARDANDO_APROVACAO
        bem.save(update_fields=['status'])

    def _bem_do_item_data(self, item_data: Dict) -> BemPatrimonial:
        bem = item_data.get('bem')
        if isinstance(bem, int):
            return BemPatrimonial.objects.get(pk=bem)
        return bem

    def _processar_itens(self, instance, itens_data, itens_atuais) -> set:
        itens_enviados_ids = set()
        for item_data in itens_data:
            bem = self._bem_do_item_data(item_data)
            if bem and bem.id in itens_atuais:
                item_existente = itens_atuais[bem.id]
                itens_enviados_ids.add(item_existente.id)
            else:
                novo_item = self._criar_novo_item(instance, bem)
                itens_enviados_ids.add(novo_item.id)
        return itens_enviados_ids

    def _criar_novo_item(self, instance, bem) -> BaixaFisicaBensItem:
        novo_item = BaixaFisicaBensItem.objects.create(baixa=instance, bem=bem)
        self._marcar_bem_em_baixa(bem)
        return novo_item

    def _remover_itens_nao_enviados(self, itens_atuais, itens_enviados_ids) -> None:
        for item in itens_atuais.values():
            if item.id not in itens_enviados_ids:
                self._restaurar_status_bem(item.bem)
                item.delete()

    @transaction.atomic
    def update(self, instance: BaixaFisicaBemPatrimonial, validated_data: Dict[str, Any]) -> BaixaFisicaBemPatrimonial:
        itens_data = validated_data.pop('itens', None)

        if itens_data is not None:
            itens_atuais = {item.bem_id: item for item in instance.itens.select_related('bem')}
            itens_enviados_ids = self._processar_itens(instance, itens_data, itens_atuais)
            self._remover_itens_nao_enviados(itens_atuais, itens_enviados_ids)

        return instance


# ============================================================================
# SERIALIZERS DE AÇÕES
# ============================================================================

class BaixaFisicaEnviarSolicitacaoSerializer(serializers.Serializer):
    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        baixa = self.context['baixa']

        if baixa.status != constants.AGUARDANDO_ENVIO:
            raise serializers.ValidationError(
                f"Não é possível enviar esta baixa. Status atual: {baixa.get_status_display()}"
            )
        if not baixa.itens.exists():
            raise serializers.ValidationError(
                "Não é possível enviar uma baixa sem itens."
            )
        return attrs


class BaixaFisicaAprovarSerializer(serializers.Serializer):
    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        baixa = self.context['baixa']
        user = self.context['request'].user

        if baixa.status != constants.SOLICITADA:
            raise serializers.ValidationError(
                f"Não é possível aprovar esta baixa. Status atual: {baixa.get_status_display()}"
            )
        if not (user.is_gestor_patrimonio or user.is_superuser):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                "Apenas Gestor de Patrimônio pode aprovar baixas físicas."
            )
        return attrs


class BaixaFisicaCancelarSerializer(serializers.Serializer):
    motivo = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Motivo do cancelamento (opcional)"
    )

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        baixa = self.context['baixa']
        user = self.context['request'].user

        if baixa.status == constants.ACEITA:
            raise serializers.ValidationError(
                "Não é possível cancelar uma baixa já aprovada."
            )
        if baixa.status not in [constants.AGUARDANDO_ENVIO, constants.SOLICITADA]:
            raise serializers.ValidationError(
                f"Não é possível cancelar esta baixa. Status atual: {baixa.get_status_display()}"
            )
        if not (user.is_gestor_patrimonio or user.is_superuser):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                "Apenas Gestor de Patrimônio pode cancelar baixas físicas."
            )
        return attrs


class BaixaFisicaSolicitarCorrecaoSerializer(serializers.Serializer):
    """
    Serializer do endpoint /solicitar-correcao/.

    Distinto de BaixaFisicaCancelarSerializer:
      - motivo é OBRIGATÓRIO aqui (no cancelar é opcional)
      - só é válido a partir do status "solicitada" (no cancelar,
        também vale para "aguardando_envio")
    """
    motivo = serializers.CharField(
        required=True,
        allow_blank=False,
        help_text="Orientações sobre o que precisa ser corrigido (obrigatório)."
    )

    def validate_motivo(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError(
                "Descreva as orientações para a correção."
            )
        return value.strip()

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        baixa = self.context['baixa']
        user = self.context['request'].user

        if baixa.status != constants.SOLICITADA:
            raise serializers.ValidationError(
                f"Não é possível solicitar correção desta baixa. "
                f"Status atual: {baixa.get_status_display()}"
            )
        # Gestor/superuser sempre pode; operador criador pode devolver sua própria baixa para correção
        is_criador = bool(getattr(baixa, "criado_por_id", None) and getattr(user, "pk", None) == baixa.criado_por_id)
        if not (user.is_gestor_patrimonio or user.is_superuser or is_criador):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied(
                "Apenas Gestor de Patrimônio ou o solicitante da baixa pode solicitar correção."
            )
        return attrs


# ============================================================================
# NBBPM CONSOLIDADA — geração em lote
# ============================================================================

class NBBPMSerializer(serializers.ModelSerializer):
    """Saída de NBBPM consolidada."""
    baixas = serializers.PrimaryKeyRelatedField(many=True, read_only=True)
    criado_por = UserSimpleSerializer(read_only=True)
    unidade_administrativa_origem = UnidadeAdministrativaSimpleSerializer(read_only=True)

    class Meta:
        model = NBBPM
        fields = [
            'id',
            'numero',
            'baixas',
            'unidade_administrativa_origem',
            'numero_processo_baixa',
            'data_autorizacao',
            'responsavel',
            'numero_processo_destinacao_final',
            'criado_por',
            'data_criacao',
        ]
        read_only_fields = fields


class NBBPMGerarLoteSerializer(serializers.Serializer):
    """Valida e cria NBBPM consolidada a partir de Baixas ACEITA da mesma UO (prefixo fixo 001)."""

    baixas = serializers.PrimaryKeyRelatedField(
        queryset=BaixaFisicaBemPatrimonial.objects.all(),
        many=True,
        required=True,
        help_text="IDs das Baixas Físicas aprovadas selecionadas.",
    )
    numero_processo_baixa = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=64,
        help_text="Número do processo de Baixa.",
    )
    data_autorizacao = serializers.DateField(
        required=True,
        help_text="Data da Autorização.",
    )
    responsavel = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=255,
        help_text="Responsável pela Baixa/geração da NBBPM.",
    )
    numero_processo_destinacao_final = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=64,
        default="",
        help_text="Número do processo de destinação final (opcional).",
    )

    def validate_numero_processo_baixa(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Informe o número do processo de Baixa.")
        return value.strip()

    def validate_responsavel(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("Informe o responsável.")
        return value.strip()

    def validate_numero_processo_destinacao_final(self, value: str) -> str:
        return (value or "").strip()

    def validate_baixas(self, baixas):
        if not baixas:
            raise serializers.ValidationError("Selecione ao menos uma Baixa Física aprovada.")
        self._validar_permissao_gerar_nbbpm()
        self._validar_escopo_baixas(baixas)
        self._validar_status_aceita(baixas)
        self._validar_uo_unica(baixas)
        self._validar_reuso_baixas(baixas)
        return baixas

    def _validar_permissao_gerar_nbbpm(self):
        user = self.context["request"].user
        if getattr(user, "is_gestor_patrimonio", False) or getattr(user, "is_superuser", False):
            return
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("Apenas Gestor de Patrimônio pode gerar NBBPM.")

    def _validar_escopo_baixas(self, baixas):
        user = self.context["request"].user
        escopo_ids = set(
            filtrar_queryset_por_escopo(
                usuario=user,
                queryset=BaixaFisicaBemPatrimonial.objects.all(),
                campo_ua="unidade_administrativa_origem",
            ).values_list("id", flat=True)
        )
        fora_do_escopo = [b for b in baixas if b.id not in escopo_ids]
        if fora_do_escopo:
            raise serializers.ValidationError("Uma ou mais Baixas selecionadas não pertencem ao seu escopo de acesso.")

    def _validar_status_aceita(self, baixas):
        nao_aprovadas = [b for b in baixas if b.status != constants.ACEITA]
        if nao_aprovadas:
            raise serializers.ValidationError("A NBBPM só pode ser gerada para Baixas Físicas com status Aprovado.")

    def _validar_uo_unica(self, baixas):
        unidades_orcamentarias = {self._extrair_uo_id(b) for b in baixas}
        if len(unidades_orcamentarias) > 1 or None in unidades_orcamentarias:
            raise serializers.ValidationError("Todas as Baixas selecionadas devem pertencer à mesma Unidade Orçamentária.")

    def _extrair_uo_id(self, baixa):
        ua = getattr(baixa, "unidade_administrativa_origem", None)
        if not ua:
            return None
        uo_id = getattr(ua, "unidade_orcamentaria_id", None)
        if uo_id is not None:
            return uo_id
        try:
            uo = getattr(ua, "unidade_orcamentaria", None)
            return getattr(uo, "pk", None) or getattr(uo, "id", None)
        except Exception:
            return None

    def _validar_reuso_baixas(self, baixas):
        ja_utilizadas = [b for b in baixas if b.nbbpms_lote.exists()]
        if ja_utilizadas:
            ids = ", ".join(str(b.id) for b in ja_utilizadas)
            raise serializers.ValidationError(f"As Baixas {ids} já possuem NBBPM gerada.")
        ja_com_numero_legado = [b for b in baixas if (b.numero_nbbpm or "").strip()]
        if ja_com_numero_legado:
            ids = ", ".join(str(b.id) for b in ja_com_numero_legado)
            raise serializers.ValidationError(f"As Baixas {ids} já possuem número NBBPM legado e não podem ser reutilizadas.")

    def create(self, validated_data):
        from bem_patrimonial.services.nbbpm_numero import criar_nbbpm_com_retry

        baixas = validated_data.pop("baixas")
        criado_por = self.context["request"].user
        nbbpm = criar_nbbpm_com_retry(
            baixas=baixas,
            criado_por=criado_por,
            **validated_data,
        )
        return nbbpm
