from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import InventarioUA, ParametroInventarioAnual
from . import constants


class InventarioUAAdminForm(forms.ModelForm):
    class Meta:
        model = InventarioUA
        fields = ("unidade_administrativa", "tipo", "periodo_final")

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        if "unidade_administrativa" in self.fields:
            self.fields["unidade_administrativa"].required = True
        if "tipo" in self.fields:
            self.fields["tipo"].required = True

        if "periodo_final" in self.fields:
            self.fields["periodo_final"].required = False

        user = getattr(self.request, "user", None)

        if (
            user
            and getattr(user, "is_operador_inventario", False)
            and not getattr(user, "is_gestor_patrimonio", False)
        ):
            ua = getattr(user, "unidade_administrativa", None)
            if not ua:
                raise ValidationError(
                    "Como operador você deve estar vinculado a uma unidade administrativa."
                )
            if "unidade_administrativa" in self.fields:
                self.fields["unidade_administrativa"].initial = ua
                self.fields["unidade_administrativa"].disabled = True

        if user and getattr(user, "is_gestor_patrimonio", False):
            ua = getattr(user, "unidade_administrativa", None)
            if ua and "unidade_administrativa" in self.fields:
                self.fields["unidade_administrativa"].initial = ua

        if self.instance and self.instance.pk:
            for f in ("unidade_administrativa", "tipo", "periodo_final"):
                if f in self.fields:
                    self.fields[f].disabled = True

    def clean(self):
        cleaned = super().clean()

        unidade_administrativa = cleaned.get("unidade_administrativa")
        tipo = cleaned.get("tipo")
        periodo_final = cleaned.get("periodo_final")

        if not tipo:
            raise ValidationError({"tipo": "Campo obrigatório."})

        if not unidade_administrativa:
            raise ValidationError({"unidade_administrativa": "Campo obrigatório."})

        if not self.instance.pk:
            existe_aberto = InventarioUA.objects.filter(
                unidade_administrativa=unidade_administrativa,
                status=constants.INVENTARIO_EM_ABERTO,
            ).exists()

            if existe_aberto:
                raise ValidationError(
                    {
                        "unidade_administrativa": (
                            "Já existe um inventário em aberto para esta Unidade Administrativa. "
                            "Feche o inventário anterior para abrir um novo."
                        )
                    }
                )

        hoje = timezone.localdate()
        ano_atual = hoje.year

        if tipo == constants.INVENTARIO_ANUAL:
            parametro = ParametroInventarioAnual.objects.filter(
                ano_referencia=ano_atual,
                ativo=True,
            ).first()

            if not parametro:
                raise ValidationError(
                    f"Não existe parâmetro ativo para inventário anual do ano {ano_atual}."
                )

            if not (parametro.periodo_inicial <= hoje <= parametro.periodo_final):
                raise ValidationError(
                    f"O inventário anual {ano_atual} só pode ser criado entre "
                    f"{parametro.periodo_inicial:%d/%m/%Y} e {parametro.periodo_final:%d/%m/%Y}."
                )

            cleaned["periodo_final"] = None

        elif tipo == constants.INVENTARIO_EVENTUAL:
            if not periodo_final:
                raise ValidationError({"periodo_final": "Este campo é obrigatório."})

        return cleaned
