from django import forms
from django.core.exceptions import ValidationError
from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.constants import APROVADO, BLOQUEADO, ENVIADA, AGUARDANDO_APROVACAO


class MovimentacaoBemPatrimonialForm(forms.ModelForm):
    def clean(self):
        self.is_cleaned = True

        created = self.instance.pk is not None
        user = self.request.user

        try:
            bem_patrimonial = self.data["bem_patrimonial"]
            unidade_origem = self.data["unidade_administrativa_origem"]
            unidade_destino = self.data["unidade_administrativa_destino"]
            quantidade = int(self.data["quantidade"])
        except Exception as e:
            raise ValidationError(e)

        try:
            bem_patrimonial = BemPatrimonial.objects.get(pk=bem_patrimonial)
        except BemPatrimonial.DoesNotExist:
            raise ValidationError(
                "Bem patrimonial não encontrado. Verifique se o bem está aprovado e sem movimentações pendentes."
            )

        if bem_patrimonial.status == AGUARDANDO_APROVACAO:
            raise ValidationError(
                f"O bem '{bem_patrimonial.nome}' está aguardando aprovação do cadastro. "
                f"Apenas bens aprovados podem ser movimentados."
            )

        if bem_patrimonial.status == BLOQUEADO:
            raise ValidationError(
                f"O bem '{bem_patrimonial.nome}' está bloqueado para movimentação. "
                f"Aguarde a resolução da movimentação pendente."
            )

        if bem_patrimonial.status != APROVADO:
            raise ValidationError(
                f"O bem '{bem_patrimonial.nome}' não pode ser movimentado. "
                f"Status atual: {bem_patrimonial.get_status_display()}. "
                f"Apenas bens aprovados podem ser movimentados."
            )

        if bem_patrimonial.tem_movimentacao_pendente:
            raise ValidationError(
                f"O bem '{bem_patrimonial.nome}' já possui uma movimentação pendente. "
                f"Aguarde a aprovação ou rejeição antes de criar nova movimentação."
            )

        try:
            origem = bem_patrimonial.unidadeadministrativabempatrimonial_set.get(
                unidade_administrativa=unidade_origem
            )
        except Exception:
            raise ValidationError(
                "Unidade origem não tem quantidade suficiente para movimentação."
            )

        if unidade_destino == unidade_origem:
            raise ValidationError("Operação não permitida.")

        if quantidade <= 0:
            raise ValidationError("Quantidade deve ser válida.")

        if origem.quantidade < quantidade:
            raise ValidationError(
                "Unidade origem não tem quantidade suficiente para movimentação."
            )

        if created:
            if user.is_operador_inventario and (
                self.instance.solicitado_por is not user
            ):
                raise ValidationError(
                    "Não é permitido alterar uma movimentação solicitada por outro usuário."
                )

        super(MovimentacaoBemPatrimonialForm, self).clean()

    def __init__(self, *args, **kwargs):
        super(MovimentacaoBemPatrimonialForm, self).__init__(*args, **kwargs)
        self.fields["bem_patrimonial"].queryset = (
            BemPatrimonial.objects.filter(status=APROVADO)
            .exclude(movimentacaobempatrimonial__status=ENVIADA)
            .distinct()
        )
