import re
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants


class _BemPatrimonialBaseMixin(serializers.Serializer):
    """
    Mixin com helpers para manter o comportamento "igual ao admin".
    """

    criado_por_nome = serializers.CharField(source="criado_por.nome", read_only=True)

    unidade_orcamentaria_codigo = serializers.CharField(
        source="unidade_administrativa.unidade_orcamentaria.codigo",
        read_only=True,
    )

    unidade_orcamentaria_nome = serializers.CharField(
        source="unidade_administrativa.unidade_orcamentaria.nome",
        read_only=True,
    )

    unidade_administrativa_codigo = serializers.CharField(
        source="unidade_administrativa.codigo",
        read_only=True,
    )
    unidade_administrativa_nome = serializers.CharField(
        source="unidade_administrativa.nome",
        read_only=True,
    )

    baixa_data = serializers.DateField(read_only=True)
    audit_last_at = serializers.DateTimeField(read_only=True)
    audit_last_by_id = serializers.IntegerField(read_only=True)

    status_display = serializers.SerializerMethodField()
    unidade_completa = serializers.SerializerMethodField()

    def get_unidade_completa(self, obj):
        ua = obj.unidade_administrativa
        if not ua:
            return None

        uo = getattr(ua, "unidade_orcamentaria", None)

        if not uo:
            return f"{ua.codigo} - {ua.nome}"

        return f"{uo.codigo} - {uo.nome} / {ua.codigo} - {ua.nome}"

    def get_status_display(self, obj):
        return obj.get_status_display()

    def _is_gestor(self, user):
        return bool(
            getattr(user, "is_gestor_patrimonio", False)
            or getattr(user, "is_superuser", False)
        )

    def _is_operador(self, user):
        return bool(getattr(user, "is_operador_inventario", False))

    def _readonly_fields_admin(self, user, obj):
        """
        Replica BemPatrimonialAdmin.get_readonly_fields.
        Observação: status/criado_por/criado_em sempre readonly no admin.
        """
        base = {"status", "criado_por", "criado_em"}

        if obj is None:
            return base

        if self._is_gestor(user):
            return base

        if self._is_operador(user):

            return base | {
                "unidade_administrativa",
                "numero_patrimonial",
                "numero_formato_antigo",
                "nome",
                "descricao",
                "valor_unitario",
                "marca",
                "modelo",
                "numero_processo",
                "foto",
                "sem_numeracao",
            }

        return base | {
            "unidade_administrativa",
            "nome",
            "descricao",
            "valor_unitario",
            "marca",
            "modelo",
            "localizacao",
            "numero_processo",
            "foto",
            "sem_numeracao",
        }

    def _validate_campos_editaveis(self, user, attrs):
        """
        Garante que usuário não está tentando alterar campos readonly do admin.
        """
        if not self.instance:
            return

        readonly = self._readonly_fields_admin(user, self.instance)
        enviados = set(attrs.keys())
        bloqueados = sorted(list(enviados.intersection(readonly)))

        if bloqueados:
            raise serializers.ValidationError(
                {
                    "detail": "Você não tem permissão para alterar alguns campos deste bem.",
                    "campos_bloqueados": bloqueados,
                }
            )

    def _parse_valor_unitario(self, raw):
        """
        - obrigatório
        - aceita "0,00" ou "0.000,00"
        - converte para Decimal
        """
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            raise serializers.ValidationError(
                {"valor_unitario": "Informe o valor unitário (obrigatório)."}
            )

        if isinstance(raw, (int, float, Decimal)):
            val = Decimal(str(raw))
            if val < 0:
                raise serializers.ValidationError(
                    {"valor_unitario": "O valor unitário não pode ser negativo."}
                )
            return val

        if not isinstance(raw, str):
            raise serializers.ValidationError(
                {"valor_unitario": "Valor inválido. Use o formato 0,00 ou 0.000,00."}
            )

        try:
            norm = raw.strip().replace(".", "").replace(",", ".")
            val = Decimal(norm)
            if val < 0:
                raise serializers.ValidationError(
                    {"valor_unitario": "O valor unitário não pode ser negativo."}
                )
            return val
        except (InvalidOperation, ValueError):
            raise serializers.ValidationError(
                {"valor_unitario": "Valor inválido. Use o formato 0,00 ou 0.000,00."}
            )

    def _validate_numero_patrimonial_form(self, cleaned):
        """
        Replica regras do admin:
        - criação: sem_numeracao e numero_formato_antigo não podem ser ambos True
        - se sem_numeracao: numero_patrimonial = None e numero_formato_antigo = False
        - se não sem_numeracao: número obrigatório
        - se não formato antigo: exige NEW_FMT_RE
        - edição: aceita SEM-NUMERO-{id} e força sem_numeracao True + formato_antigo False
        """
        sem = bool(cleaned.get("sem_numeracao"))
        antigo = bool(cleaned.get("numero_formato_antigo"))
        numero = cleaned.get("numero_patrimonial")

        if isinstance(numero, str):
            numero = numero.strip() or None

        tem_pk = bool(self.instance and getattr(self.instance, "pk", None))

        NEW_FMT_RE = r"^\d{3}\.\d{9}-\d$"
        SEM_NUM_RE = r"^SEM-NUMERO-\d+$"

        if tem_pk:
            if numero:
                if sem and re.fullmatch(SEM_NUM_RE, numero):
                    cleaned["sem_numeracao"] = True
                    cleaned["numero_formato_antigo"] = False
                    return cleaned

                if not antigo and not re.fullmatch(NEW_FMT_RE, numero):
                    raise serializers.ValidationError(
                        {
                            "numero_patrimonial": "Use o formato 000.000000000-0 ou marque 'Formato antigo'."
                        }
                    )
            else:
                if not sem:
                    raise serializers.ValidationError(
                        {
                            "numero_patrimonial": "Informe o Número Patrimonial ou marque 'Sem numeração'."
                        }
                    )
                cleaned["numero_formato_antigo"] = False
            return cleaned

        if sem and antigo:
            raise serializers.ValidationError(
                "Selecione 'Formato antigo' OU 'Sem numeração' — não ambos."
            )

        if sem:
            cleaned["numero_patrimonial"] = None
            cleaned["numero_formato_antigo"] = False
            return cleaned

        if not numero:
            raise serializers.ValidationError(
                {
                    "numero_patrimonial": "Informe o Número Patrimonial ou marque 'Sem numeração'."
                }
            )

        if not antigo and not re.fullmatch(NEW_FMT_RE, numero):
            raise serializers.ValidationError(
                {
                    "numero_patrimonial": "Use o formato 000.000000000-0 ou marque 'Formato antigo'."
                }
            )

        cleaned["numero_patrimonial"] = numero
        return cleaned


class BemPatrimonialListSerializer(
    _BemPatrimonialBaseMixin, serializers.ModelSerializer
):
    class Meta:
        model = BemPatrimonial
        fields = [
            "id",
            "numero_patrimonial",
            "nome",
            "status",
            "status_display",
            "unidade_completa",
            "unidade_orcamentaria_codigo",
            "unidade_orcamentaria_nome",
            "unidade_administrativa_codigo",
            "unidade_administrativa_nome",
        ]
        read_only_fields = fields


class BemPatrimonialDetailSerializer(
    _BemPatrimonialBaseMixin, serializers.ModelSerializer
):
    class Meta:
        model = BemPatrimonial
        fields = [
            "id",
            "status",
            "status_display",
            "unidade_administrativa",
            "unidade_administrativa_codigo",
            "unidade_administrativa_nome",
            "numero_patrimonial",
            "numero_formato_antigo",
            "sem_numeracao",
            "nome",
            "descricao",
            "valor_unitario",
            "marca",
            "modelo",
            "localizacao",
            "numero_processo",
            "foto",
            "bloqueado_conciliacao",
            "criado_por",
            "criado_por_nome",
            "criado_em",
            "atualizado_em",
            "baixa_data",
            "audit_last_at",
            "audit_last_by_id",
        ]
        read_only_fields = [
            "id",
            "status",
            "criado_por",
            "criado_em",
            "atualizado_em",
            "baixa_data",
            "audit_last_at",
            "audit_last_by_id",
        ]

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if self.instance:
            if getattr(self.instance, "excluido", False):
                raise serializers.ValidationError(
                    "Este bem está excluído e não pode ser editado."
                )

            if self.instance.status == constants.BAIXA_FISICA:
                raise serializers.ValidationError(
                    "Este bem está com status 'Baixa Física' e não pode ser editado."
                )

        if self.instance and "unidade_administrativa" in attrs:
            if attrs["unidade_administrativa"] != self.instance.unidade_administrativa:
                raise serializers.ValidationError(
                    {
                        "unidade_administrativa": "Não é permitido alterar a Unidade Administrativa na edição."
                    }
                )

        self._validate_campos_editaveis(user, attrs)

        incoming_vu = attrs.get("valor_unitario", None)
        if incoming_vu is not None:
            attrs["valor_unitario"] = self._parse_valor_unitario(incoming_vu)
        else:
            if not self.instance:
                raise serializers.ValidationError(
                    {"valor_unitario": "Informe o valor unitário (obrigatório)."}
                )

        cleaned = dict(attrs)
        if self.instance:
            for k in ("numero_patrimonial", "sem_numeracao", "numero_formato_antigo"):
                if k not in cleaned:
                    cleaned[k] = getattr(self.instance, k)

        cleaned = self._validate_numero_patrimonial_form(cleaned)
        attrs.update(
            {
                "numero_patrimonial": cleaned.get("numero_patrimonial"),
                "sem_numeracao": cleaned.get("sem_numeracao"),
                "numero_formato_antigo": cleaned.get("numero_formato_antigo"),
            }
        )

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        validated_data["criado_por"] = user
        validated_data["status"] = constants.AGUARDANDO_APROVACAO

        try:
            return super().create(validated_data)
        except IntegrityError as e:
            if "numero_patrimonial" in str(e).lower():
                raise serializers.ValidationError(
                    {
                        "numero_patrimonial": "Não foi possível salvar. O Número Patrimonial já está cadastrado no sistema."
                    }
                )
            raise

    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except IntegrityError as e:
            if "numero_patrimonial" in str(e).lower():
                raise serializers.ValidationError(
                    {
                        "numero_patrimonial": "Não foi possível salvar. O Número Patrimonial já está cadastrado no sistema."
                    }
                )
            raise
        except DjangoValidationError as e:
            if hasattr(e, "message_dict"):
                raise serializers.ValidationError(e.message_dict)
            raise serializers.ValidationError(str(e))
