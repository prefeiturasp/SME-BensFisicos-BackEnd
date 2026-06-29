from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.urls import reverse
from django.db import transaction
from typing import Dict, Any

from .models import BaixaFisicaBemPatrimonial, BaixaFisicaBensItem, BemPatrimonial
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.escopo import filtrar_ua_origem_por_escopo
from . import constants

User = get_user_model()

_STATUS_BEM_INVALIDOS_PARA_BAIXA = {
    constants.BAIXA_FISICA_AGUARDANDO_APROVACAO,
    constants.BLOQUEADO,
    *constants.STATUS_FINAIS_BEM,
}


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
    # Usa SerializerMethodField para sobrescrever "Aguardando envio" → "Em elaboração"
    status_display = serializers.SerializerMethodField()
    total_itens = serializers.SerializerMethodField()

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


class BaixaFisicaBemPatrimonialDetailSerializer(serializers.ModelSerializer):
    unidade_administrativa_origem = UnidadeAdministrativaSimpleSerializer(read_only=True)
    criado_por = UserSimpleSerializer(read_only=True)
    aprovado_por = UserSimpleSerializer(read_only=True)
    status_display = serializers.SerializerMethodField()
    itens = BaixaFisicaBensItemSerializer(many=True, read_only=True)

    url_solicitar = serializers.SerializerMethodField()
    url_aprovar = serializers.SerializerMethodField()
    url_recusar = serializers.SerializerMethodField()
    url_gerar_nbbpm = serializers.SerializerMethodField()

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
            'url_gerar_nbbpm',
        ]
        read_only_fields = fields

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

    def get_url_gerar_nbbpm(self, obj: BaixaFisicaBemPatrimonial):
        if obj.status == constants.ACEITA and obj.numero_nbbpm:
            return self._build_url('baixas-fisicas-gerar-nbbpm', obj.id)
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
