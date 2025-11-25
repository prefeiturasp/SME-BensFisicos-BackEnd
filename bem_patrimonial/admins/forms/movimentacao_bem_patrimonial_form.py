from django import forms
from django.core.exceptions import ValidationError

from bem_patrimonial.models import MovimentacaoBemPatrimonial
from dados_comuns.models import UnidadeAdministrativa


class MovimentacaoBemPatrimonialForm(forms.ModelForm):
    class Meta:
        model = MovimentacaoBemPatrimonial

        exclude = (
            "solicitado_por",
            "aprovado_por",
            "rejeitado_por",
            "cancelado_por",
            "status",
            "bem_patrimonial",
            "bens",
        )

    def __init__(self, *args, **kwargs):
        super(MovimentacaoBemPatrimonialForm, self).__init__(*args, **kwargs)

        if "unidade_administrativa_origem" in self.fields:
            self.fields["unidade_administrativa_origem"].queryset = (
                UnidadeAdministrativa.objects.filter(status=UnidadeAdministrativa.ATIVA)
            )

        if "unidade_administrativa_destino" in self.fields:
            self.fields["unidade_administrativa_destino"].queryset = (
                UnidadeAdministrativa.objects.filter(status=UnidadeAdministrativa.ATIVA)
            )

    def clean(self):
        cleaned_data = super().clean()
        self.is_cleaned = True

        user = getattr(self, "request", None).user if hasattr(self, "request") else None
        is_editing = self.instance.pk is not None

        if not is_editing:
            ua_origem = cleaned_data.get("unidade_administrativa_origem")
            ua_destino = cleaned_data.get("unidade_administrativa_destino")

            if not ua_origem:
                raise ValidationError("Unidade administrativa de origem é obrigatória.")

            if not ua_destino:
                raise ValidationError(
                    "Unidade administrativa de destino é obrigatória."
                )

            if not ua_origem.is_ativa:
                raise ValidationError(
                    f"A unidade de origem '{ua_origem.nome}' está inativa. "
                    "Não é possível criar movimentações a partir de unidades inativas."
                )

            if not ua_destino.is_ativa:
                raise ValidationError(
                    f"A unidade de destino '{ua_destino.nome}' está inativa. "
                    "Não é possível criar movimentações para unidades inativas."
                )

            if ua_destino == ua_origem:
                raise ValidationError(
                    "Operação não permitida: origem e destino são iguais."
                )

        if is_editing and user and getattr(user, "is_operador_inventario", False):
            if self.instance.solicitado_por_id != user.id:
                raise ValidationError(
                    "Não é permitido alterar uma movimentação solicitada por outro usuário."
                )

        return cleaned_data
