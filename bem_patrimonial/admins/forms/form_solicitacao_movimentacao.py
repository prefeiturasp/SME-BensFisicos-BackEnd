from django import forms
from django.core.exceptions import ValidationError
from bem_patrimonial.models import BemPatrimonial, APROVADO


class SolicitacaoMovimentacaoBemPatrimonialForm(forms.ModelForm):

    def clean(self):
        self.is_cleaned = True
        if self.instance.pk is not None:
            if self.request.user.is_operador_inventario and \
                    (self.instance.solicitado_por is not self.request.user):
                raise ValidationError("Não é permitido alterar uma movimentação solicitada por outro usuário.")
        super(SolicitacaoMovimentacaoBemPatrimonialForm, self).clean()

    def __init__(self, *args, **kwargs):
        super(SolicitacaoMovimentacaoBemPatrimonialForm, self).__init__(*args, **kwargs)
        self.fields['bem_patrimonial'].queryset = BemPatrimonial.objects.filter(status=APROVADO)
