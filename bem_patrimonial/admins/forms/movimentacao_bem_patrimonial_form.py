from django import forms
from django.core.exceptions import ValidationError

from bem_patrimonial.models import MovimentacaoBemPatrimonial
from dados_comuns.models import UnidadeAdministrativa

from dados_comuns.escopo import (
    filtrar_ua_origem_por_escopo,
    filtrar_ua_destino_por_uo_do_usuario,
)


class MovimentacaoBemPatrimonialForm(forms.ModelForm):
    class Meta:
        model = MovimentacaoBemPatrimonial
        fields = (
            "unidade_administrativa_origem",
            "unidade_administrativa_destino",
            "observacao",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        user = None
        if hasattr(self, "request") and getattr(self.request, "user", None):
            user = self.request.user

        qs_ativas = UnidadeAdministrativa.objects.filter(
            status=UnidadeAdministrativa.ATIVA
        )

        if user:
            if "unidade_administrativa_origem" in self.fields:
                self.fields["unidade_administrativa_origem"].queryset = (
                    filtrar_ua_origem_por_escopo(user, qs_ativas)
                )

            if "unidade_administrativa_destino" in self.fields:
                self.fields["unidade_administrativa_destino"].queryset = (
                    filtrar_ua_destino_por_uo_do_usuario(user, qs_ativas)
                )
        else:

            if "unidade_administrativa_origem" in self.fields:
                self.fields["unidade_administrativa_origem"].queryset = qs_ativas
            if "unidade_administrativa_destino" in self.fields:
                self.fields["unidade_administrativa_destino"].queryset = qs_ativas

    def _validate_ua_origem_destino_new(self, cleaned_data, user):
        ua_origem = cleaned_data.get("unidade_administrativa_origem")
        ua_destino = cleaned_data.get("unidade_administrativa_destino")
        if not ua_origem:
            raise ValidationError(
                {"unidade_administrativa_origem": "Unidade administrativa de origem é obrigatória."}
            )
        if not ua_destino:
            raise ValidationError(
                {"unidade_administrativa_destino": "Unidade administrativa de destino é obrigatória."}
            )
        if not ua_origem.is_ativa:
            raise ValidationError(
                {
                    "unidade_administrativa_origem": (
                        f"A unidade de origem '{ua_origem.nome}' está inativa. "
                        "Não é possível criar movimentações a partir de unidades inativas."
                    )
                }
            )
        if not ua_destino.is_ativa:
            raise ValidationError(
                {
                    "unidade_administrativa_destino": (
                        f"A unidade de destino '{ua_destino.nome}' está inativa. "
                        "Não é possível criar movimentações para unidades inativas."
                    )
                }
            )
        if ua_destino == ua_origem:
            raise ValidationError("Operação não permitida: origem e destino são iguais.")
        if not user:
            return
        qs_origem = filtrar_ua_origem_por_escopo(user, UnidadeAdministrativa.objects.all())
        if not qs_origem.filter(pk=ua_origem.pk).exists():
            raise ValidationError(
                {"unidade_administrativa_origem": "UA de origem fora do seu escopo de acesso."}
            )
        qs_destino = filtrar_ua_destino_por_uo_do_usuario(
            user, UnidadeAdministrativa.objects.all()
        )
        if not qs_destino.filter(pk=ua_destino.pk).exists():
            raise ValidationError(
                {"unidade_administrativa_destino": "UA de destino fora das UAs permitidas para sua UO."}
            )

    def clean(self):
        cleaned_data = super().clean()
        self.is_cleaned = True
        user = getattr(self, "request", None).user if hasattr(self, "request") else None
        is_editing = self.instance.pk is not None
        if not is_editing:
            self._validate_ua_origem_destino_new(cleaned_data, user)
        if is_editing and user and getattr(user, "is_operador_inventario", False):
            if self.instance.solicitado_por_id != user.id:
                raise ValidationError(
                    "Não é permitido alterar uma movimentação solicitada por outro usuário."
                )
        return cleaned_data
