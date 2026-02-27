from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date

from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.escopo import filtrar_ua_origem_por_escopo, usuario_e_super_admin

from .models import ConciliacaoUA, ParametroConciliacaoAnual
from . import constants


class ConciliacaoUAAdminForm(forms.ModelForm):
    class Meta:
        model = ConciliacaoUA
        fields = ("unidade_administrativa", "tipo", "periodo_final")

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        user = getattr(self.request, "user", None)

        if not self.instance.pk and "tipo" in self.fields:
            self.fields["tipo"].choices = [
                (constants.CONCILIACAO_EVENTUAL, "Eventual"),
            ]
            self.fields["tipo"].initial = constants.CONCILIACAO_EVENTUAL
            self.fields["tipo"].disabled = True

        if "unidade_administrativa" in self.fields:
            self.fields["unidade_administrativa"].required = True
            
        if "tipo" in self.fields:
            self.fields["tipo"].required = True
            
        if "periodo_final" in self.fields:
            self.fields["periodo_final"].required = False

        if user and "unidade_administrativa" in self.fields:
            base_qs = UnidadeAdministrativa.objects.filter(
                status=UnidadeAdministrativa.ATIVA
            )
            allowed_qs = filtrar_ua_origem_por_escopo(user, base_qs)
            self.fields["unidade_administrativa"].queryset = allowed_qs

            ua_user = getattr(user, "unidade_administrativa", None)
            if ua_user and ua_user.is_ativa and not usuario_e_super_admin(user):
                self.fields["unidade_administrativa"].initial = ua_user
                self.fields["unidade_administrativa"].disabled = True

        if self.instance and self.instance.pk:
            for f in ("unidade_administrativa", "tipo", "periodo_final"):
                if f in self.fields:
                    self.fields[f].disabled = True

    def clean(self):
        cleaned = super().clean()

        user = getattr(self.request, "user", None)

        unidade_administrativa = cleaned.get("unidade_administrativa")
        tipo = cleaned.get("tipo")
        periodo_final = cleaned.get("periodo_final")

        if not tipo:
            raise ValidationError({"tipo": "Campo obrigatório."})

        if not unidade_administrativa:
            raise ValidationError({"unidade_administrativa": "Campo obrigatório."})

        if user:
            base_qs = UnidadeAdministrativa.objects.filter(
                status=UnidadeAdministrativa.ATIVA
            )
            allowed_qs = filtrar_ua_origem_por_escopo(user, base_qs)

            ua_user = getattr(user, "unidade_administrativa", None)
            if ua_user and ua_user.is_ativa and not usuario_e_super_admin(user):
                cleaned["unidade_administrativa"] = ua_user
                unidade_administrativa = ua_user

            if not allowed_qs.filter(pk=unidade_administrativa.pk).exists():
                raise ValidationError(
                    {
                        "unidade_administrativa": "Você não tem permissão para usar esta Unidade Administrativa."
                    }
                )

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

            uo_id = getattr(unidade_administrativa, "unidade_orcamentaria_id", None)

            parametro = ParametroConciliacaoAnual.objects.filter(
                unidade_orcamentaria_id=uo_id,
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

        elif tipo == constants.CONCILIACAO_EVENTUAL and not periodo_final:
            raise ValidationError({"periodo_final": "Este campo é obrigatório."})

        return cleaned
