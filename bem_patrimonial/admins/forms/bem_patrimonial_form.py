from django import forms
from django.core.exceptions import ValidationError
from bem_patrimonial import constants
from bem_patrimonial.models import BemPatrimonial
import re
from django.forms.utils import ErrorDict


class BemPatrimonialAdminForm(forms.ModelForm):
    CADASTRO_MODO_CHOICES = (("unico", "Único Bem"), ("multi", "Múltiplos Bens"))
    cadastro_modo = forms.ChoiceField(
        label="Cadastrar",
        choices=CADASTRO_MODO_CHOICES,
        widget=forms.RadioSelect,
        required=False,
        initial="unico",
        help_text="Selecione o modo de cadastro antes de preencher os campos.",
    )

    class Meta:
        model = BemPatrimonial
        fields = "__all__"
        widgets = {
            "valor_unitario": forms.TextInput(
                attrs={
                    "placeholder": "0,00",
                    "inputmode": "decimal",
                    "autocomplete": "off",
                    "pattern": r"^\d{1,3}(\.\d{3})*,\d{2}$",
                }
            ),
            "numero_patrimonial": forms.TextInput(
                attrs={
                    "placeholder": "000.000000000-0",
                    "autocomplete": "off",
                    "inputmode": "numeric",
                    "pattern": r"^\d{3}\.\d{9}-\d$",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        vu_widget = getattr(self.Meta, "widgets", {}).get(
            "valor_unitario", forms.TextInput(attrs={"placeholder": "0,00"})
        )
        self.fields["valor_unitario"] = forms.CharField(
            required=True,
            label=(
                self.fields.get("valor_unitario", None).label
                if "valor_unitario" in self.fields
                else "Valor unitário"
            ),
            widget=vu_widget,
        )

        if "localizacao" in self.fields:
            self.fields["localizacao"].required = True
            if not self.fields["localizacao"].label:
                self.fields["localizacao"].label = "Localização"

        if "status" in self.fields:
            self.fields["status"].disabled = True
            if not (self.instance and self.instance.pk):
                self.initial.setdefault("status", constants.AGUARDANDO_APROVACAO)

        if self.instance and self.instance.pk:
            self.fields["cadastro_modo"].widget = forms.HiddenInput()
            if "sem_numeracao" in self.fields:
                self.fields["sem_numeracao"].disabled = True

    def _post_clean(self):
        has_np_error = False
        if hasattr(self, "errors") and isinstance(self.errors, ErrorDict):
            has_np_error = "numero_patrimonial" in self.errors

        if has_np_error:
            original_clean = getattr(self.instance, "clean", None)
            try:

                if original_clean:
                    self.instance.clean = lambda: None
                super()._post_clean()
            finally:
                if original_clean:
                    self.instance.clean = original_clean
            return

        super()._post_clean()

    def clean_valor_unitario(self):
        from decimal import Decimal

        raw = (self.data.get("valor_unitario") or "").strip()
        if not raw:
            raise ValidationError("Informe o valor unitário (obrigatório).")
        try:
            norm = raw.replace(".", "").replace(",", ".")
            val = Decimal(norm)
            if val < 0:
                raise ValidationError("O valor unitário não pode ser negativo.")
            return val
        except Exception:
            raise ValidationError("Valor inválido. Use o formato 0,00 ou 0.000,00.")

    def clean(self):

        cleaned = super().clean()

        if not (self.instance and self.instance.pk):
            cleaned.setdefault("status", constants.AGUARDANDO_APROVACAO)

        sem = bool(cleaned.get("sem_numeracao"))
        antigo = bool(cleaned.get("numero_formato_antigo"))
        numero = (cleaned.get("numero_patrimonial") or "").strip()
        tem_pk = bool(getattr(self.instance, "pk", None))

        NEW_FMT_RE = r"^\d{3}\.\d{9}-\d$"
        SEM_NUM_RE = r"^SEM-NUMERO-\d+$"

        if tem_pk:
            if numero:

                if sem and re.fullmatch(SEM_NUM_RE, numero):
                    cleaned["sem_numeracao"] = True
                    cleaned["numero_formato_antigo"] = False
                    return cleaned

                if not antigo and not re.fullmatch(NEW_FMT_RE, numero):
                    raise ValidationError(
                        {
                            "numero_patrimonial": "Use o formato 000.000000000-0 ou marque 'Formato antigo'."
                        }
                    )
            else:

                if not sem:
                    raise ValidationError(
                        {
                            "numero_patrimonial": "Informe o Número Patrimonial ou marque 'Sem numeração'."
                        }
                    )

                cleaned["numero_formato_antigo"] = False

            return cleaned

        if sem and antigo:
            raise ValidationError(
                "Selecione 'Formato antigo' OU 'Sem numeração' — não ambos."
            )

        if sem:

            cleaned["numero_patrimonial"] = None
            cleaned["numero_formato_antigo"] = False
            return cleaned

        if not numero:
            raise ValidationError(
                {
                    "numero_patrimonial": "Informe o Número Patrimonial ou marque 'Sem numeração'."
                }
            )

        if not antigo and not re.fullmatch(NEW_FMT_RE, numero):
            raise ValidationError(
                {
                    "numero_patrimonial": "Use o formato 000.000000000-0 ou marque 'Formato antigo'."
                }
            )

        return cleaned

    def validate_unique(self):
        """Mensagem personalizada para duplicidade do número patrimonial."""
        try:
            return super().validate_unique()
        except ValidationError as e:
            if "numero_patrimonial" in getattr(e, "message_dict", {}):
                raise ValidationError(
                    {
                        "numero_patrimonial": [
                            "Não foi possível salvar. O Número Patrimonial já está cadastrado no sistema."
                        ]
                    }
                )
            raise
