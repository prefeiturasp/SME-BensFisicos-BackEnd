from django import forms
from django.core.exceptions import ValidationError
from bem_patrimonial.models import BemPatrimonial
import re


class BemPatrimonialForm(forms.ModelForm):
    class Meta:
        model = BemPatrimonial
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        sem = bool(cleaned.get("sem_numeracao"))
        antigo = bool(cleaned.get("numero_formato_antigo"))
        numero = cleaned.get("numero_patrimonial")

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
