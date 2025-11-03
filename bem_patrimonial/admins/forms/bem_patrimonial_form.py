from django import forms
from django.core.exceptions import ValidationError
from bem_patrimonial import constants
from bem_patrimonial.models import BemPatrimonial


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

        # garante required + reaproveita o widget configurado na Meta (fallback seguro)
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

        # status desabilitado; default na criação
        if "status" in self.fields:
            self.fields["status"].disabled = True
            if not (self.instance and self.instance.pk):
                self.initial.setdefault("status", constants.AGUARDANDO_APROVACAO)

        # na edição, oculta o rádio e desabilita 'sem_numeracao'
        if self.instance and self.instance.pk:
            self.fields["cadastro_modo"].widget = forms.HiddenInput()
            if "sem_numeracao" in self.fields:
                self.fields["sem_numeracao"].disabled = True

    def _post_clean(self):
        """
        Na edição, se veio número patrimonial, ignorar a flag sem_numeracao
        apenas para a validação do model.clean/unique.
        """
        if self.instance and self.instance.pk:
            np = self.cleaned_data.get("numero_patrimonial")
            if np:
                original_sem = bool(self.instance.sem_numeracao)
                try:
                    self.instance.sem_numeracao = False
                    super()._post_clean()
                finally:
                    self.instance.sem_numeracao = original_sem
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

        # default de status na criação
        if not (self.instance and self.instance.pk):
            cleaned.setdefault("status", constants.AGUARDANDO_APROVACAO)

        sem = bool(cleaned.get("sem_numeracao"))
        antigo = bool(cleaned.get("numero_formato_antigo"))
        numero = cleaned.get("numero_patrimonial")

        # não permitir marcar os dois
        if sem and antigo:
            raise ValidationError(
                "Selecione 'Formato antigo' OU 'Sem numeração' — não ambos."
            )

        if sem:
            cleaned["numero_patrimonial"] = None
            cleaned["numero_formato_antigo"] = False

        if not sem and not (numero and str(numero).strip()):
            raise ValidationError(
                {
                    "numero_patrimonial": "Informe o Número Patrimonial ou marque 'Sem numeração'."
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
