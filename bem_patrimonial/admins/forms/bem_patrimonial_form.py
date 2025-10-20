from django import forms
from django.core.exceptions import ValidationError
from bem_patrimonial.models import BemPatrimonial
import re


class BemPatrimonialForm(forms.ModelForm):
    class Meta:
        model = BemPatrimonial
        fields = "__all__"
        widgets = {
            "numero_patrimonial": forms.TextInput(
                attrs={
                    "placeholder": "000.000000000-0",
                    "data-mask-npat": "1",  # usado no JS do admin
                    "autocomplete": "off",
                }
            ),
        }

    def clean(self):
        cleaned = super().clean()
        antigo = cleaned.get("numero_formato_antigo")
        sem = cleaned.get("sem_numeracao")
        num = (cleaned.get("numero_patrimonial") or "").strip()

        if sem:
            cleaned["numero_formato_antigo"] = False

        if antigo and sem:
            raise ValidationError(
                "Selecione 'Formato antigo' OU 'Sem numeração' — não ambos."
            )

        if not sem and not num:
            raise ValidationError(
                {
                    "numero_patrimonial": "Informe o Número Patrimonial ou marque 'Sem numeração'."
                }
            )

        if not antigo and not sem:
            if not re.fullmatch(r"^\d{3}\.\d{9}-\d$", num):
                raise ValidationError(
                    {"numero_patrimonial": "Número Patrimonial incompleto"}
                )

        if sem:
            cleaned["numero_patrimonial"] = None

        return cleaned

    def validate_unique(self):
        """Mensagem personalizada para duplicidade"""
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
