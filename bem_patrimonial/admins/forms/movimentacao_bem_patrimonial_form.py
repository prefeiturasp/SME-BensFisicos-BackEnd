from django import forms
from django.core.exceptions import ValidationError
from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.constants import APROVADO


class MovimentacaoBemPatrimonialForm(forms.ModelForm):
    def clean(self):
        self.is_cleaned = True

        created = self.instance.pk is not None
        user = self.request.user

        try:
            bem_patrimonial = self.data['bem_patrimonial']
            unidade_origem = self.data['unidade_administrativa_origem']
            unidade_destino = self.data['unidade_administrativa_destino']
            quantidade = int(self.data['quantidade'])
        except Exception as e:
            raise ValidationError(e)

        try:
            bem_patrimonial = BemPatrimonial.objects.get(pk=bem_patrimonial)
        except BemPatrimonial.DoesNotExist as e:
            raise ValidationError(e)

        try:
            origem = bem_patrimonial.unidadeadministrativabempatrimonial_set.get(
                unidade_administrativa=unidade_origem
            )
        except Exception:
            raise ValidationError("Unidade origem não tem quantidade suficiente para movimentação.")

        if unidade_destino == unidade_origem:
            raise ValidationError("Operação não permitida.")

        if quantidade <= 0:
            raise ValidationError("Quantidade deve ser válida.")

        if (origem.quantidade < quantidade):
            raise ValidationError("Unidade origem não tem quantidade suficiente para movimentação.")

        if created:
            if user.is_operador_inventario and (self.instance.solicitado_por is not user):
                raise ValidationError("Não é permitido alterar uma movimentação solicitada por outro usuário.")

        super(MovimentacaoBemPatrimonialForm, self).clean()

    def __init__(self, *args, **kwargs):
        super(MovimentacaoBemPatrimonialForm, self).__init__(*args, **kwargs)
        self.fields['bem_patrimonial'].queryset = BemPatrimonial.objects.filter(status=APROVADO)
