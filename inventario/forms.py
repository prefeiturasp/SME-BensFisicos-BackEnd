from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date

from .models import ConciliacaoUA, ParametroConciliacaoAnual
from . import constants


class ConciliacaoUAAdminForm(forms.ModelForm):
    class Meta:
        model = ConciliacaoUA
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
            existe_aberto = ConciliacaoUA.objects.filter(
                unidade_administrativa=unidade_administrativa,
                status=constants.CONCILIACAO_EM_ABERTO,
            ).exists()

            if existe_aberto:
                raise ValidationError(
                    {
                        "unidade_administrativa": (
                            "Já existe uma conciliação em aberto para esta Unidade Administrativa. "
                            "Feche a conciliação anterior para abrir uma nova."
                        )
                    }
                )

        hoje = timezone.localdate()
        ano_corrente = hoje.year

        if tipo == constants.CONCILIACAO_ANUAL:
            ano_referencia = hoje.year - 1

            parametro = ParametroConciliacaoAnual.objects.filter(
                ano_referencia=ano_referencia,
                ativo=True,
            ).first()

            if parametro:
                data_inicio = parametro.periodo_inicial
                data_fim = parametro.periodo_final
            else:
                data_inicio = date(ano_corrente, 1, 1)
                data_fim = date(ano_corrente, 3, 31)

            if not (data_inicio <= hoje <= data_fim):
                raise ValidationError(
                    f"A conciliação anual {ano_referencia} só pode ser criada entre "
                    f"{data_inicio:%d/%m/%Y} e {data_fim:%d/%m/%Y}."
                )

            cleaned["periodo_final"] = date(ano_referencia, 12, 31)

        elif tipo == constants.CONCILIACAO_EVENTUAL:
            if not periodo_final:
                raise ValidationError({"periodo_final": "Este campo é obrigatório."})

        return cleaned
