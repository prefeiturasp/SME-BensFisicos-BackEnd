from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from bem_patrimonial.models import TransferenciaBemPatrimonial
from bem_patrimonial.admins.forms.transferencia_bem_patrimonial_form import (
    TransferenciaBemPatrimonialForm,
)
from bem_patrimonial.admins.inlines.inlines import TransferenciaBensItemInline
from dados_comuns.escopo import filtrar_queryset_transferencia_por_escopo


class TransferenciaBemPatrimonialAdmin(admin.ModelAdmin):
    model = TransferenciaBemPatrimonial
    form = TransferenciaBemPatrimonialForm
    inlines = [TransferenciaBensItemInline]

    create_fields = (
        "unidade_orcamentaria_origem",
        "unidade_orcamentaria_destino",
        "numero_processo",
        "observacao",
        "unidade_administrativa_filtro",
    )
    change_fields = (
        "numero_ntbpm",
        "get_documento_ntbpm_link",
        "unidade_orcamentaria_origem",
        "unidade_orcamentaria_destino",
        "unidade_administrativa_destino",
        "numero_processo",
        "observacao",
        "criado_por",
        "efetivado_por",
        "criado_em",
        "efetivado_em",
    )

    list_display = (
        "id",
        "numero_processo",
        "unidade_orcamentaria_origem",
        "unidade_orcamentaria_destino",
        "criado_por",
        "efetivado_em",
    )
    search_fields = (
        "numero_processo",
        "numero_ntbpm",
        "unidade_orcamentaria_origem__codigo",
        "unidade_orcamentaria_origem__nome",
        "unidade_orcamentaria_destino__codigo",
        "unidade_orcamentaria_destino__nome",
        "itens__bem__numero_patrimonial",
        "itens__bem__nome",
    )
    search_help_text = (
        "Pesquise por número do processo, UO de origem/destino e número patrimonial ou nome do bem."
    )
    readonly_fields = (
        "numero_ntbpm",
        "get_documento_ntbpm_link",
        "unidade_orcamentaria_origem",
        "unidade_orcamentaria_destino",
        "unidade_administrativa_destino",
        "numero_processo",
        "observacao",
        "criado_por",
        "efetivado_por",
        "criado_em",
        "efetivado_em",
    )

    class Media:
        js = (
            "js/bem_patrimonial/prevenir_duplo_submit.js",
            "admin/transferencia_filtra_bens_por_uo.js",
        )
        css = {
            "all": (
                "css/prevenir_duplo_submit.css",
                "css/custom_inline.css",
                "css/hide_crud_icons.css",
            )
        }

    def _usuario_pode_acessar(self, user):
        return bool(getattr(user, "is_gestor_patrimonio", False))

    def has_module_permission(self, request):
        return self._usuario_pode_acessar(request.user)

    def has_view_permission(self, request, obj=None):
        return self._usuario_pode_acessar(request.user)

    def has_add_permission(self, request):
        return self._usuario_pode_acessar(request.user)

    def has_change_permission(self, request, obj=None):
        return self._usuario_pode_acessar(request.user)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_fields(self, request, obj=None):
        if obj is None:
            return self.create_fields
        return self.change_fields

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return self.readonly_fields

    def get_form(self, request, obj=None, **kwargs):
        form_class = super().get_form(request, obj, **kwargs)

        class RequestForm(form_class):
            def __init__(self_inner, *a, **kw):
                kw["request"] = request
                super().__init__(*a, **kw)

        return RequestForm

    def get_queryset(self, request):
        qs = (
            super()
            .get_queryset(request)
            .select_related(
                "unidade_orcamentaria_origem",
                "unidade_orcamentaria_destino",
                "unidade_administrativa_destino",
                "criado_por",
                "efetivado_por",
            )
        )
        return filtrar_queryset_transferencia_por_escopo(request.user, qs).distinct()

    def save_model(self, request, obj, form, change):
        if obj.pk is None:
            obj.criado_por = request.user
        obj.unidade_administrativa_destino = form.cleaned_data[
            "unidade_administrativa_destino"
        ]
        super().save_model(request, obj, form, change)

    def get_documento_ntbpm_link(self, obj):
        if obj and obj.numero_ntbpm:
            url_protegida = reverse("download_documento_ntbpm", kwargs={"pk": obj.pk})
            return format_html(
                '<a href="{}" target="_blank">Baixar documento NTBPM</a>',
                url_protegida,
            )
        return "Número NTBPM não gerado"

    get_documento_ntbpm_link.short_description = "Documento NTBPM"

    def _get_changeform_extra_context(self, object_id=None, extra_context=None):
        context = dict(extra_context or {})

        if object_id is not None:
            context.update(
                {
                    "show_save": False,
                    "show_save_and_continue": False,
                    "show_save_and_add_another": False,
                    "show_save_as_new": False,
                    "show_delete": False,
                    "show_delete_link": False,
                    "show_close": True,
                }
            )

        return context

    def get_bens_transferidos_links(self, obj):
        itens = list(
            obj.itens.select_related("bem", "bem__unidade_administrativa").order_by(
                "bem__numero_patrimonial", "bem__nome"
            )
        )
        if not itens:
            return "Nenhum bem vinculado"

        return format_html(
            "<ul>{}</ul>",
            format_html_join(
                "",
                '<li><a href="{}" target="_blank">{}</a> <span>({})</span></li>',
                (
                    (
                        reverse(
                            "admin:bem_patrimonial_bempatrimonial_change",
                            args=[item.bem_id],
                        ),
                        str(item.bem),
                        str(getattr(item.bem, "unidade_administrativa", "-")),
                    )
                    for item in itens
                ),
            ),
        )

    get_bens_transferidos_links.short_description = "Bens transferidos"

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if object_id is not None and request.method == "POST":
            raise PermissionDenied(
                "Transferencias existentes estao disponiveis apenas para visualizacao."
            )

        with transaction.atomic():
            return super().changeform_view(
                request,
                object_id,
                form_url,
                self._get_changeform_extra_context(object_id, extra_context),
            )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        transferencia = form.instance
        if not change and not transferencia.efetivado_em:
            transferencia.efetivar_transferencia(request.user)

    def get_inline_formsets(self, request, formsets, inline_instances, obj=None):
        inline_formsets = super().get_inline_formsets(
            request, formsets, inline_instances, obj
        )

        if obj is not None:
            for formset in inline_formsets:
                formset.can_add = False
                formset.can_delete = False
        return inline_formsets