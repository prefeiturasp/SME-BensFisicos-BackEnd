from functools import lru_cache

from django.forms.models import BaseInlineFormSet, ModelForm
from django.core.exceptions import ValidationError
from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils.html import format_html

from bem_patrimonial.models import (
    MovimentacaoBensItem,
    BemPatrimonial,
    TransferenciaBensItem,
)
from bem_patrimonial.constants import (
    APROVADO,
    BLOQUEADO,
    ENVIADA,
    AGUARDANDO_APROVACAO,
)
from dados_comuns.models import HistoricoGeral


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


def _formatar_identificacao_bem_transferencia(bem):
    numero_patrimonial = bem.numero_patrimonial or "SEM-NUMERO"
    nome = bem.nome or "Sem nome"
    unidade_administrativa = getattr(bem, "unidade_administrativa", None)
    if unidade_administrativa:
        return f"{unidade_administrativa} | {numero_patrimonial} - {nome}"
    return f"{numero_patrimonial} - {nome}"


def _normalizar_valor_historico_unidade_administrativa(valor):
    if not valor:
        return "-"

    prefixo, separador, restante = valor.partition(" - ")
    if separador and prefixo.isdigit():
        return restante
    return valor


@lru_cache(maxsize=1)
def _content_type_bem_patrimonial_id():
    return ContentType.objects.get_for_model(BemPatrimonial).id


def _obter_ua_origem_item_transferencia(item):
    historico = (
        HistoricoGeral.objects.filter(
            content_type_id=_content_type_bem_patrimonial_id(),
            object_id=str(item.bem_id),
            campo="unidade_administrativa",
        )
        .order_by("-alterado_em")
        .first()
    )

    if historico and historico.valor_antigo:
        return _normalizar_valor_historico_unidade_administrativa(
            historico.valor_antigo
        )

    unidade_administrativa = getattr(item.bem, "unidade_administrativa", None)
    return str(unidade_administrativa) if unidade_administrativa else "-"


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


class TransferenciaBensItemInlineFormSet(BaseInlineFormSet):
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
            raise ValidationError("Adicione ao menos um bem na transferência.")


class TransferenciaBensItemInlineForm(ModelForm):
    class Meta:
        model = TransferenciaBensItem
        fields = ("bem",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "bem" not in self.fields:
            return

        def _label(obj: BemPatrimonial):
            return _formatar_identificacao_bem_transferencia(obj)

        self.fields["bem"].label_from_instance = _label


class TransferenciaBensItemInline(admin.TabularInline):
    model = TransferenciaBensItem
    extra = 1
    form = TransferenciaBensItemInlineForm
    formset = TransferenciaBensItemInlineFormSet
    autocomplete_fields = ("bem",)
    can_delete = False
    template = "admin/edit_inline/transferencia_bens_tabular.html"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            "bem",
            "bem__unidade_administrativa",
        )

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("bem",)
        return ("bem_detalhado",)

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return ("bem_detalhado",)

    def get_extra(self, request, obj=None, **kwargs):
        if obj is None:
            return self.extra
        return 0

    def bem_detalhado(self, obj):
        numero_patrimonial = obj.bem.numero_patrimonial or "SEM-NUMERO"
        nome = obj.bem.nome or "Sem nome"
        unidade_administrativa = _obter_ua_origem_item_transferencia(obj)
        return format_html(
            '{} | <a href="{}" target="_blank">{} - {}</a>',
            unidade_administrativa,
            reverse("admin:bem_patrimonial_bempatrimonial_change", args=[obj.bem_id]),
            numero_patrimonial,
            nome,
        )

    bem_detalhado.short_description = "UA de origem | Bem patrimonial"

    def has_add_permission(self, request, obj=None):

        return obj is None
