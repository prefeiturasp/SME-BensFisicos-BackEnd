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

# Status de bens que impedem inclusão em nova baixa
_STATUS_BEM_INVALIDOS_PARA_BAIXA = {
    constants.BAIXA_FISICA_AGUARDANDO_APROVACAO,
    constants.BAIXA_FISICA,
    constants.BLOQUEADO,
}


# ============================================================================
# SERIALIZERS DE MODELOS RELACIONADOS
# ============================================================================

class UnidadeAdministrativaSimpleSerializer(serializers.ModelSerializer):
    """Serializer simplificado de Unidade Administrativa"""

    class Meta:
        model = UnidadeAdministrativa
        fields = ['id', 'nome', 'sigla', 'codigo', 'status']
        read_only_fields = fields


class UserSimpleSerializer(serializers.ModelSerializer):
    """Serializer simplificado de Usuário"""

    nome_completo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'nome_completo', 'email']
        read_only_fields = fields

    def get_nome_completo(self, obj: User) -> str:
        return obj.get_full_name() or obj.username


class BemPatrimonialSimpleSerializer(serializers.ModelSerializer):
    """Serializer simplificado de Bem Patrimonial"""

    class Meta:
        model = BemPatrimonial
        fields = ['id', 'numero_patrimonial', 'nome', 'descricao', 'status']
        read_only_fields = fields


# ============================================================================
# SERIALIZERS DE BAIXA FÍSICA ITEM
# ============================================================================

class BaixaFisicaBensItemSerializer(serializers.ModelSerializer):
    """Serializer para itens da baixa física (leitura)"""

    bem = BemPatrimonialSimpleSerializer(read_only=True)

    class Meta:
        model = BaixaFisicaBensItem
        fields = ['id', 'bem']
        read_only_fields = fields


class BaixaFisicaBensItemCreateSerializer(serializers.ModelSerializer):
    """Serializer para criar/atualizar itens da baixa física"""

    class Meta:
        model = BaixaFisicaBensItem
        fields = ['id', 'bem']

    def validate_bem(self, value: BemPatrimonial) -> BemPatrimonial:
        if not value:
            raise serializers.ValidationError("Bem patrimonial é obrigatório.")

        # ISSUE #2 — rejeitar bens com status inválido para baixa
        if value.status in _STATUS_BEM_INVALIDOS_PARA_BAIXA:
            baixa_id = self.context.get('baixa_id')

            # Se está aguardando aprovação, verificar se é da mesma baixa (edição)
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
# SERIALIZERS DE BAIXA FÍSICA
# ============================================================================

class BaixaFisicaBemPatrimonialListSerializer(serializers.ModelSerializer):
    """Serializer simplificado para listagem de baixas físicas"""

    unidade_administrativa_origem = UnidadeAdministrativaSimpleSerializer(read_only=True)
    criado_por = UserSimpleSerializer(read_only=True)
    aprovado_por = UserSimpleSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
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

    def get_total_itens(self, obj: BaixaFisicaBemPatrimonial) -> int:
        return obj.itens.count()


class BaixaFisicaBemPatrimonialDetailSerializer(serializers.ModelSerializer):
    """Serializer completo para detalhamento de baixa física"""

    unidade_administrativa_origem = UnidadeAdministrativaSimpleSerializer(read_only=True)
    criado_por = UserSimpleSerializer(read_only=True)
    aprovado_por = UserSimpleSerializer(read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    itens = BaixaFisicaBensItemSerializer(many=True, read_only=True)

    url_enviar_solicitacao = serializers.SerializerMethodField()
    url_aprovar = serializers.SerializerMethodField()
    url_cancelar = serializers.SerializerMethodField()
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
            'url_enviar_solicitacao',
            'url_aprovar',
            'url_cancelar',
            'url_gerar_nbbpm',
        ]
        read_only_fields = fields

    def _build_url(self, viewname: str, pk: int) -> str | None:
        request = self.context.get('request')
        if not request:
            return None
        path = reverse(viewname, kwargs={'pk': pk})
        return request.build_absolute_uri(path)

    def _usuario_e_gestor(self) -> bool:
        request = self.context.get('request')
        if not request or not request.user or not request.user.is_authenticated:
            return False
        user = request.user
        return user.is_gestor_patrimonio or user.is_superuser

    def get_url_enviar_solicitacao(self, obj: BaixaFisicaBemPatrimonial):
        if obj.status == constants.AGUARDANDO_ENVIO:
            return self._build_url('baixas-fisicas-enviar-solicitacao', obj.id)
        return None

    def get_url_aprovar(self, obj: BaixaFisicaBemPatrimonial):
        if obj.status == constants.SOLICITADA and self._usuario_e_gestor():
            return self._build_url('baixas-fisicas-aprovar', obj.id)
        return None

    def get_url_cancelar(self, obj: BaixaFisicaBemPatrimonial):
        if obj.status in [constants.AGUARDANDO_ENVIO, constants.SOLICITADA] and self._usuario_e_gestor():
            return self._build_url('baixas-fisicas-cancelar', obj.id)
        return None

    def get_url_gerar_nbbpm(self, obj: BaixaFisicaBemPatrimonial):
        if obj.status == constants.ACEITA and obj.numero_nbbpm:
            return self._build_url('baixas-fisicas-gerar-nbbpm', obj.id)
        return None


class BaixaFisicaBemPatrimonialCreateSerializer(serializers.ModelSerializer):
    """Serializer para criar baixa física"""

    itens = BaixaFisicaBensItemCreateSerializer(many=True)

    class Meta:
        model = BaixaFisicaBemPatrimonial
        fields = [
            'numero_processo_baixa',
            'unidade_administrativa_origem',
            'data_baixa',
            'itens',
        ]

    def validate_itens(self, value: list) -> list:
        if not value:
            raise serializers.ValidationError(
                "É necessário informar ao menos um bem para a baixa física."
            )
        return value

    def validate_data_baixa(self, value):
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

        # Valida escopo: rejeita UA fora do escopo do usuário autenticado,
        # espelhando a lógica do Django Admin (filtrar_ua_origem_por_escopo).
        # Superadmins e gestores sem UA vinculada têm acesso irrestrito.
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
        """
        ISSUE #2 — validação de escopo: os bens incluídos devem pertencer
        à UA de origem informada no payload.
        """
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
            status=constants.AGUARDANDO_ENVIO
        )

        for item_data in itens_data:
            BaixaFisicaBensItem.objects.create(baixa=baixa, **item_data)
            self._atualizar_status_bem(item_data['bem'], constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)

        return baixa


class BaixaFisicaBemPatrimonialUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer para atualizar baixa física.

    Alinhado com o Django Admin: após a criação, apenas os itens (bens) podem
    ser alterados. Campos como numero_processo_baixa e data_baixa ficam travados,
    exatamente como o Admin define em get_readonly_fields().
    """

    itens = serializers.ListField(child=serializers.DictField(), write_only=True)

    class Meta:
        model = BaixaFisicaBemPatrimonial
        # Somente itens é editável após a criação — espelha o Admin.
        fields = ['itens']

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        instance = self.instance
        if instance.status != constants.AGUARDANDO_ENVIO:
            raise serializers.ValidationError(
                "Apenas baixas com status 'Aguardando envio' podem ser editadas."
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
        """Resolve o bem a partir do dict (pode ser instância ou pk)."""
        bem = item_data.get('bem')
        if isinstance(bem, int):
            return BemPatrimonial.objects.get(pk=bem)
        return bem

    def _processar_itens(
        self,
        instance: BaixaFisicaBemPatrimonial,
        itens_data: list,
        itens_atuais: Dict,  # Dict[bem_id -> BaixaFisicaBensItem]
    ) -> set:
        """
        Percorre os itens enviados pelo cliente.
        Se o bem já existe na baixa → mantém o item.
        Se o bem é novo → cria item novo.
        Retorna o conjunto de IDs de itens que devem ser mantidos.
        """
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

    def _criar_novo_item(self, instance: BaixaFisicaBemPatrimonial, bem: BemPatrimonial) -> BaixaFisicaBensItem:
        novo_item = BaixaFisicaBensItem.objects.create(baixa=instance, bem=bem)
        self._marcar_bem_em_baixa(bem)
        return novo_item

    def _remover_itens_nao_enviados(self, itens_atuais: Dict, itens_enviados_ids: set) -> None:
        for item in itens_atuais.values():
            if item.id not in itens_enviados_ids:
                self._restaurar_status_bem(item.bem)
                item.delete()

    @transaction.atomic
    def update(self, instance: BaixaFisicaBemPatrimonial, validated_data: Dict[str, Any]) -> BaixaFisicaBemPatrimonial:
        # Apenas itens são editáveis — não há campos escalares para atualizar.
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
    """Serializer para enviar solicitação"""

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
    """Serializer para aprovar baixa"""

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
    """Serializer para cancelar baixa"""

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
