from django import forms

from dados_comuns.escopo import uas_acessiveis_para_importacao
from dados_comuns.models import UnidadeAdministrativa
from import_export.forms import ConfirmImportForm, ImportForm


def _usuario_precisa_selecionar_ua(user) -> bool:
    """
    True quando o usuário opera no nível de UO (não possui UA direta) e,
    portanto, precisa escolher a Unidade Administrativa de destino na
    importação. Espelha a regra do frontend da API.
    """
    if user is None:
        return False
    return getattr(user, "unidade_administrativa_id", None) is None


class BemPatrimonialImportForm(ImportForm):
    """
    Formulário da 1ª etapa da importação no Admin.

    Exibe o campo de Unidade Administrativa de destino apenas quando o usuário
    está logado numa UO (sem UA direta). As opções são exatamente as UAs em que
    o usuário pode importar (uas_acessiveis_para_importacao), as mesmas do
    seletor da API.
    """

    unidade_administrativa = forms.ModelChoiceField(
        queryset=UnidadeAdministrativa.objects.none(),
        required=False,
        label="Unidade Administrativa de destino",
        help_text="Selecione a Unidade Administrativa em que os Bens serão incorporados.",
    )

    def __init__(self, *args, **kwargs):
        # ImportExportFormBase aceita 'user' via kwargs em algumas versões;
        # lemos de forma tolerante para não quebrar a assinatura.
        self._user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if _usuario_precisa_selecionar_ua(self._user):
            self.fields["unidade_administrativa"].queryset = (
                uas_acessiveis_para_importacao(self._user)
            )
            self.fields["unidade_administrativa"].required = True
        else:
            # Usuário logado numa UA: destino é a própria UA; o campo não se aplica.
            self.fields.pop("unidade_administrativa", None)


class BemPatrimonialConfirmImportForm(ConfirmImportForm):
    """
    Formulário da 2ª etapa (confirmação). Carrega a UA escolhida na 1ª etapa
    num campo oculto, para que ela persista até a gravação efetiva dos bens.
    """

    unidade_administrativa = forms.IntegerField(
        required=False, widget=forms.HiddenInput()
    )
