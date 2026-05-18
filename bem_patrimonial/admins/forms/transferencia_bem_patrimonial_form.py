from django import forms
from django.core.exceptions import ValidationError

from bem_patrimonial.models import TransferenciaBemPatrimonial
from bem_patrimonial.admins.forms.movimentacao_bem_patrimonial_form import (
    MENSAGEM_SEM_PONTO_CENTRAL,
    obter_ua_ponto_central,
    obter_uo_referencia_do_usuario,
    queryset_uas_da_uo,
)
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria
from dados_comuns.utils import PREFIXO_CODIGO_UO_SME


def queryset_uos_destino_externas():
    return UnidadeOrcamentaria.objects.filter(ativa=True).exclude(
        codigo__startswith=PREFIXO_CODIGO_UO_SME
    ).order_by("codigo", "nome")


class TransferenciaBemPatrimonialForm(forms.ModelForm):
    unidade_administrativa_filtro = forms.ModelChoiceField(
        label="Filtrar bens por unidade administrativa",
        queryset=UnidadeAdministrativa.objects.none(),
        required=False,
        empty_label="Todas as UAs da UO de origem",
        help_text=(
            "Use este filtro para localizar bens de uma UA específica. "
            "Os bens já adicionados permanecem na lista mesmo quando o filtro mudar."
        ),
    )

    class Meta:
        model = TransferenciaBemPatrimonial
        fields = (
            "unidade_orcamentaria_origem",
            "unidade_orcamentaria_destino",
            "numero_processo",
            "observacao",
        )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        user = self._get_user()
        uo_origem = obter_uo_referencia_do_usuario(user)

        self._configurar_campos_iniciais(uo_origem)

        if self.instance.pk:
            self._configurar_campos_edicao()
            return

        self._configurar_campos_criacao(uo_origem)

    def _configurar_campos_iniciais(self, uo_origem):
        if "unidade_orcamentaria_origem" in self.fields:
            self.fields["unidade_orcamentaria_origem"].queryset = UnidadeOrcamentaria.objects.none()

        if "unidade_orcamentaria_destino" in self.fields:
            self.fields["unidade_orcamentaria_destino"].queryset = queryset_uos_destino_externas()

        if "unidade_administrativa_filtro" in self.fields and uo_origem:
            self.fields["unidade_administrativa_filtro"].queryset = queryset_uas_da_uo(
                uo_origem
            )

    def _configurar_campos_edicao(self):
        if "unidade_orcamentaria_origem" in self.fields:
            self.fields["unidade_orcamentaria_origem"].queryset = UnidadeOrcamentaria.objects.filter(
                pk=self.instance.unidade_orcamentaria_origem_id
            )
            self.fields["unidade_orcamentaria_origem"].disabled = True

        if "unidade_orcamentaria_destino" in self.fields:
            self.fields["unidade_orcamentaria_destino"].queryset = UnidadeOrcamentaria.objects.filter(
                pk=self.instance.unidade_orcamentaria_destino_id
            )
            self.fields["unidade_orcamentaria_destino"].disabled = True

        for field_name in ("numero_processo", "observacao"):
            if field_name in self.fields:
                self.fields[field_name].disabled = True

        if "unidade_administrativa_filtro" in self.fields:
            self.fields["unidade_administrativa_filtro"].queryset = queryset_uas_da_uo(
                self.instance.unidade_orcamentaria_origem
            )
            self.fields["unidade_administrativa_filtro"].disabled = True

    def _configurar_campos_criacao(self, uo_origem):
        if "unidade_orcamentaria_origem" not in self.fields:
            return

        if uo_origem:
            self.fields["unidade_orcamentaria_origem"].queryset = UnidadeOrcamentaria.objects.filter(
                pk=uo_origem.pk
            )
            self.fields["unidade_orcamentaria_origem"].initial = uo_origem.pk

        self.fields["unidade_orcamentaria_origem"].disabled = True

    def _get_user(self):
        if getattr(self, "request", None) and getattr(self.request, "user", None):
            return self.request.user
        return None

    def clean(self):
        cleaned_data = super().clean()
        user = self._get_user()
        uo_origem = getattr(self.instance, "unidade_orcamentaria_origem", None)

        if not self.instance.pk:
            uo_origem = obter_uo_referencia_do_usuario(user)
            if not uo_origem:
                raise ValidationError(
                    {
                        "unidade_orcamentaria_origem": "Não foi possível identificar a UO de origem do usuário."
                    }
                )
            cleaned_data["unidade_orcamentaria_origem"] = uo_origem

        uo_destino = cleaned_data.get("unidade_orcamentaria_destino")
        if not uo_destino:
            raise ValidationError(
                {
                    "unidade_orcamentaria_destino": "Unidade Orçamentária de destino é obrigatória."
                }
            )

        if uo_origem and uo_destino.pk == uo_origem.pk:
            raise ValidationError(
                {
                    "unidade_orcamentaria_destino": "A UO de destino deve ser diferente da UO de origem."
                }
            )

        ua_destino = obter_ua_ponto_central(uo_destino)
        if not ua_destino:
            raise ValidationError(
                {
                    "unidade_orcamentaria_destino": MENSAGEM_SEM_PONTO_CENTRAL
                }
            )

        cleaned_data["unidade_administrativa_destino"] = ua_destino
        return cleaned_data