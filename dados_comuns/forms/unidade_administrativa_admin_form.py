from django import forms
from django.core.exceptions import ValidationError
import re

from dados_comuns.models import UnidadeAdministrativa


class UnidadeAdministrativaAdminForm(forms.ModelForm):
    codigo_sufixo = forms.CharField(
        label="Código (final)",
        required=True,
        max_length=3,
        help_text="Digite apenas os 3 últimos dígitos. Ex: 286",
    )

    class Meta:
        model = UnidadeAdministrativa
        fields = ("unidade_orcamentaria", "codigo_sufixo", "sigla", "nome", "status")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk and self.instance.codigo:
            codigo = (self.instance.codigo or "").strip()
            if "." in codigo:
                self.fields["codigo_sufixo"].initial = codigo.split(".")[-1]
            else:

                self.fields["codigo_sufixo"].initial = codigo

    def clean_codigo_sufixo(self):
        v = (self.cleaned_data.get("codigo_sufixo") or "").strip()
        if not re.fullmatch(r"\d{1,3}", v):
            raise ValidationError("Informe até 3 dígitos (ex: 286).")
        return v.zfill(3)

    def clean(self):
        cleaned = super().clean()

        uo = cleaned.get("unidade_orcamentaria")
        sufixo = cleaned.get("codigo_sufixo")

        if not uo:
            raise ValidationError(
                {"unidade_orcamentaria": "Unidade Orçamentária é obrigatória."}
            )

        if not sufixo:
            raise ValidationError(
                {"codigo_sufixo": "Informe os 3 últimos dígitos do código."}
            )

        cleaned["codigo"] = f"{uo.codigo.strip()}.{sufixo}"

        return cleaned
