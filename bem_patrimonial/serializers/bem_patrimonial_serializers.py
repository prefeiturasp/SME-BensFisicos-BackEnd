import os
import re
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants
from dados_comuns.models import UnidadeAdministrativa


class _BemPatrimonialBaseMixin(serializers.Serializer):
    """
    Mixin com helpers para manter o comportamento "igual ao admin".
    """

    criado_por_nome = serializers.CharField(source="criado_por.nome", read_only=True)
    criado_por_rf = serializers.CharField(source="criado_por.rf", read_only=True)

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
        bloqueados = sorted(enviados.intersection(readonly))

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

    _NEW_FMT_RE = r"^\d{3}\.\d{9}-\d$"
    _SEM_NUM_RE = r"^SEM-NUMERO-\d+$"
    _MSG_NUMERO_FORMATO_INVALIDO = (
        "Use o formato 000.000000000-0 ou marque 'Formato antigo'."
    )
    _MSG_NUMERO_OBRIGATORIO_OU_SEM_NUM = (
        "Informe o Número Patrimonial ou marque 'Sem numeração'."
    )

    def _validate_numero_edicao(self, cleaned, sem, antigo, numero):
        """Valida número patrimonial na edição (tem_pk)."""
        if numero:
            if sem and re.fullmatch(self._SEM_NUM_RE, numero):
                cleaned["sem_numeracao"] = True
                cleaned["numero_formato_antigo"] = False
                return cleaned
            if not antigo and not re.fullmatch(self._NEW_FMT_RE, numero):
                raise serializers.ValidationError(
                    {"numero_patrimonial": self._MSG_NUMERO_FORMATO_INVALIDO}
                )
        else:
            if not sem:
                raise serializers.ValidationError(
                    {"numero_patrimonial": self._MSG_NUMERO_OBRIGATORIO_OU_SEM_NUM}
                )
            cleaned["numero_formato_antigo"] = False
        return cleaned

    def _validate_numero_criacao(self, cleaned, sem, antigo, numero):
        """Valida número patrimonial na criação."""
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
                {"numero_patrimonial": self._MSG_NUMERO_OBRIGATORIO_OU_SEM_NUM}
            )
        if not antigo and not re.fullmatch(self._NEW_FMT_RE, numero):
            raise serializers.ValidationError(
                {"numero_patrimonial": self._MSG_NUMERO_FORMATO_INVALIDO}
            )
        cleaned["numero_patrimonial"] = numero
        return cleaned

    def _validate_numero_patrimonial_form(self, cleaned):
        """
        Replica regras do admin (criação e edição).
        """
        sem = bool(cleaned.get("sem_numeracao"))
        antigo = bool(cleaned.get("numero_formato_antigo"))
        numero = cleaned.get("numero_patrimonial")
        if isinstance(numero, str):
            numero = numero.strip() or None

        tem_pk = bool(self.instance and getattr(self.instance, "pk", None))
        if tem_pk:
            return self._validate_numero_edicao(cleaned, sem, antigo, numero)
        return self._validate_numero_criacao(cleaned, sem, antigo, numero)


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


# Campos que disparam obrigatoriedade de justificativa
_CAMPOS_QUE_EXIGEM_JUSTIFICATIVA = {"nome", "numero_patrimonial"}


class BemPatrimonialDetailSerializer(
    _BemPatrimonialBaseMixin, serializers.ModelSerializer
):
    # Write-only: nunca retorna ao frontend, só usado para salvar no histórico
    justificativa = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        default="",
    )

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
            "observacao",
            "valor_unitario",
            "marca",
            "modelo",
            "localizacao",
            "numero_processo",
            "foto",
            "bloqueado_conciliacao",
            "criado_por",
            "criado_por_nome",
            "criado_por_rf",
            "criado_em",
            "atualizado_em",
            "baixa_data",
            "audit_last_at",
            "audit_last_by_id",
            # justificativa declarada acima como write_only
            "justificativa",
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
            "bloqueado_conciliacao",
        ]

    def _validate_instance_edit_restrictions(self, attrs):
        """Valida restrições de edição (excluído, baixa física, UA)."""
        if not self.instance:
            return
        if getattr(self.instance, "excluido", False):
            raise serializers.ValidationError(
                "Este bem está excluído e não pode ser editado."
            )
        if self.instance.status in constants.STATUS_FINAIS_BEM:
            raise serializers.ValidationError(
                f"Este bem está com status '{self.instance.get_status_display()}' e não pode ser editado."
            )
        if "unidade_administrativa" in attrs and attrs["unidade_administrativa"] != self.instance.unidade_administrativa:
            raise serializers.ValidationError(
                {
                    "unidade_administrativa": "Não é permitido alterar a Unidade Administrativa na edição."
                }
            )

    def _validate_valor_unitario_incoming(self, attrs):
        """Garante valor_unitario preenchido e parseado."""
        incoming_vu = attrs.get("valor_unitario", None)
        if incoming_vu is not None:
            attrs["valor_unitario"] = self._parse_valor_unitario(incoming_vu)
        elif not self.instance:
            raise serializers.ValidationError(
                {"valor_unitario": "Informe o valor unitário (obrigatório)."}
            )

    def _validate_justificativa(self, attrs):
        """
        Justificativa obrigatória quando nome ou numero_patrimonial mudam na edição.
        Nunca obrigatória na criação.
        """
        if not self.instance:
            return

        campos_alterados = _CAMPOS_QUE_EXIGEM_JUSTIFICATIVA.intersection(attrs.keys())
        if not campos_alterados:
            return

        mudou = any(
            str(attrs[campo]) != str(getattr(self.instance, campo, ""))
            for campo in campos_alterados
        )
        if not mudou:
            return

        justificativa = attrs.get("justificativa", "").strip()
        if not justificativa:
            raise serializers.ValidationError(
                {
                    "justificativa": (
                        "Justificativa é obrigatória ao alterar nome ou número patrimonial."
                    )
                }
            )

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        self._validate_instance_edit_restrictions(attrs)
        self._validate_campos_editaveis(user, attrs)
        self._validate_valor_unitario_incoming(attrs)

        erros_combinados = {}

        cleaned = dict(attrs)
        if self.instance:
            for k in ("numero_patrimonial", "sem_numeracao", "numero_formato_antigo"):
                if k not in cleaned:
                    cleaned[k] = getattr(self.instance, k)

        try:
            cleaned = self._validate_numero_patrimonial_form(cleaned)
        except serializers.ValidationError as exc:
            detail = exc.detail
            if isinstance(detail, dict):
                erros_combinados.update(detail)
            else:
                erros_combinados["numero_patrimonial"] = detail

        try:
            self._validate_justificativa(attrs)
        except serializers.ValidationError as exc:
            detail = exc.detail
            if isinstance(detail, dict):
                erros_combinados.update(detail)
            else:
                erros_combinados["justificativa"] = detail

        if erros_combinados:
            raise serializers.ValidationError(erros_combinados)

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

        # justificativa não é campo do model — descarta silenciosamente na criação
        validated_data.pop("justificativa", None)

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
        # Extrai justificativa antes de passar ao model (não é campo do DB)
        justificativa = validated_data.pop("justificativa", "").strip() or None

        # Injeta no instance para que o signal de auditoria do model a capture
        instance._justificativa = justificativa

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
        finally:
            # Limpa o atributo temporário independente do resultado
            if hasattr(instance, "_justificativa"):
                del instance._justificativa


class BemItemCriacaoSerializer(serializers.Serializer):
    """Dados únicos de cada bem na criação em lote."""

    numero_patrimonial = serializers.CharField(required=False, allow_blank=True, default="")
    numero_formato_antigo = serializers.BooleanField(required=False, default=False)
    sem_numeracao = serializers.BooleanField(required=False, default=False)
    localizacao = serializers.CharField(required=False, allow_blank=True, default="")


class BemPatrimonialMultiCreateSerializer(_BemPatrimonialBaseMixin, serializers.Serializer):
    """
    Criação em lote: dados base compartilhados + lista de bens (multi_payload).

    Valida todos os bens antes de persistir qualquer um — se qualquer número
    patrimonial for inválido ou duplicado (no payload ou no banco), nenhum bem é criado.
    """

    unidade_administrativa = serializers.PrimaryKeyRelatedField(
        queryset=UnidadeAdministrativa.objects.all()
    )
    nome = serializers.CharField()
    descricao = serializers.CharField()
    valor_unitario = serializers.CharField()
    marca = serializers.CharField()
    modelo = serializers.CharField()
    numero_processo = serializers.CharField(required=False, allow_blank=True, default="")
    observacao = serializers.CharField(required=False, allow_blank=True, default="")
    multi_payload = BemItemCriacaoSerializer(many=True)

    def _validate_item_multi_payload(self, item, numeros_vistos):
        item_errors = {}
        sem = bool(item.get("sem_numeracao"))
        antigo = bool(item.get("numero_formato_antigo"))
        numero = (item.get("numero_patrimonial") or "").strip() or None

        if sem and antigo:
            item_errors["numero_patrimonial"] = (
                "Selecione 'Formato antigo' OU 'Sem numeração' — não ambos."
            )
            return item_errors

        if sem:
            return item_errors

        if not numero:
            item_errors["numero_patrimonial"] = self._MSG_NUMERO_OBRIGATORIO_OU_SEM_NUM
            return item_errors

        if not antigo and not re.fullmatch(self._NEW_FMT_RE, numero):
            item_errors["numero_patrimonial"] = self._MSG_NUMERO_FORMATO_INVALIDO
            return item_errors

        if numero in numeros_vistos:
            item_errors["numero_patrimonial"] = (
                "Número patrimonial duplicado neste cadastro."
            )
            return item_errors

        if BemPatrimonial.objects.filter(numero_patrimonial=numero, excluido=False).exists():
            item_errors["numero_patrimonial"] = (
                "Número Patrimonial já está cadastrado no sistema."
            )
            return item_errors

        numeros_vistos.add(numero)
        return item_errors

    def validate(self, attrs):
        attrs["valor_unitario"] = self._parse_valor_unitario(attrs.get("valor_unitario"))

        multi_payload = attrs.get("multi_payload", [])
        if not multi_payload:
            raise serializers.ValidationError(
                {"multi_payload": "Informe ao menos um bem."}
            )
        linhas_errors = {}
        numeros_vistos = set()

        for i, item in enumerate(multi_payload):
            item_errors = self._validate_item_multi_payload(item, numeros_vistos)

            if item_errors:
                linhas_errors[str(i)] = item_errors

        if linhas_errors:
            raise serializers.ValidationError({"linhas": linhas_errors})

        return attrs


# ---------------------------------------------------------------------------
# Importação via planilha
# ---------------------------------------------------------------------------

class ImportacaoBemPatrimonialSerializer(serializers.Serializer):
    """
    Serializer de entrada para importação em lote via planilha.

    Valida apenas o arquivo recebido — toda a lógica de negócio
    (UA/UO, número patrimonial, duplicidade, status, sem_numeracao, etc.)
    fica no BemPatrimonialResource, garantindo paridade total com o Admin.
    """

    arquivo = serializers.FileField(
        help_text=(
            "Planilha com os bens a importar. "
            "Formatos aceitos: XLSX, XLS, CSV. "
            "Tamanho máximo: 10 MB."
        )
    )

    def validate_arquivo(self, value):
        max_bytes = 10 * 1024 * 1024  # 10 MB
        if value.size > max_bytes:
            raise serializers.ValidationError(
                "O arquivo excede o tamanho máximo permitido de 10 MB."
            )

        _, ext = os.path.splitext((value.name or "").lower())
        formatos_aceitos = {".xlsx", ".xls", ".csv"}
        if ext not in formatos_aceitos:
            raise serializers.ValidationError(
                f"Formato de arquivo não suportado: '{value.name}'. "
                "Use XLSX, XLS ou CSV."
            )

        return value
