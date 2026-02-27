from django.forms.models import BaseInlineFormSet, ModelForm
from django.core.exceptions import ValidationError
from django.contrib import admin

from bem_patrimonial.models import (
    MovimentacaoBensItem,
    BemPatrimonial,
)
from bem_patrimonial.constants import (
    APROVADO,
    BLOQUEADO,
    ENVIADA,
    AGUARDANDO_APROVACAO,
)


def _raise_bem_bloqueado_inventario(bem, item_bloqueante=None):
    if item_bloqueante:
        msg = (
            f"O bem '{bem.nome}' está bloqueado pelo inventário "
            f"'{item_bloqueante.conciliacao.numero_conciliacao}'. "
            f"Verifique a situação do bem no inventário antes de movimentá-lo."
        )
    else:
        msg = (
            f"O bem '{bem.nome}' está bloqueado por inventário. "
            f"Verifique a situação do bem no inventário antes de movimentá-lo."
        )
    raise ValidationError(msg)


def _validate_bem_para_movimentacao(bem):
    if bem.status == AGUARDANDO_APROVACAO:
        raise ValidationError(
            f"O bem '{bem.nome}' está aguardando aprovação do cadastro. "
            f"Apenas bens aprovados podem ser movimentados."
        )
    if bem.status == BLOQUEADO:
        raise ValidationError(
            f"O bem '{bem.nome}' está bloqueado para movimentação. "
            f"Aguarde a resolução da movimentação pendente."
        )
    if getattr(bem, "bloqueado_conciliacao", False):
        from inventario.models import ItemConciliacao
        from inventario import constants as inv_constants

        item_bloqueante = (
            ItemConciliacao.objects.filter(
                bem=bem,
                conciliacao__status=inv_constants.CONCILIACAO_EM_ABERTO,
            )
            .filter(situacao=inv_constants.EM_PROCESSO_BAIXA_FISICA)
            .select_related("conciliacao")
            .first()
        )
        _raise_bem_bloqueado_inventario(bem, item_bloqueante)
    if bem.status != APROVADO:
        raise ValidationError(
            f"O bem '{bem.nome}' não pode ser movimentado. "
            f"Status atual: {bem.get_status_display()}. "
            f"Apenas bens aprovados podem ser movimentados."
        )
    if getattr(bem, "tem_movimentacao_pendente", False):
        raise ValidationError(
            f"O bem '{bem.nome}' já possui uma movimentação pendente. "
            f"Aguarde a aprovação ou rejeição antes de criar nova movimentação."
        )


class MovimentacaoBensItemInlineFormSet(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for form in self.forms:
            if "DELETE" in form.fields:
                form.fields["DELETE"].disabled = True
                form.fields["DELETE"].widget.attrs["onclick"] = "return false;"

    def clean(self):
        super().clean()

        if any(self.errors):
            return

        bens_usados = []
        for form in self.forms:
            if form.cleaned_data.get("DELETE", False):
                continue
            bem = form.cleaned_data.get("bem")
            if not bem:
                continue
            bens_usados.append(bem)
            _validate_bem_para_movimentacao(bem)

        if not bens_usados:
            raise ValidationError("Adicione ao menos um bem na movimentação.")


class MovimentacaoBensItemInlineForm(ModelForm):
    class Meta:
        model = MovimentacaoBensItem
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        def _label(obj: BemPatrimonial):
            npat = obj.numero_patrimonial or "SEM-NUMERO"
            return f"{npat} - {obj.nome} ({obj.marca} / {obj.modelo})"

        self.fields["bem"].label_from_instance = _label


class MovimentacaoBensItemInline(admin.TabularInline):
    model = MovimentacaoBensItem
    extra = 1
    form = MovimentacaoBensItemInlineForm
    formset = MovimentacaoBensItemInlineFormSet
    autocomplete_fields = ("bem",)

    def has_add_permission(self, request, obj=None):

        return obj is None
