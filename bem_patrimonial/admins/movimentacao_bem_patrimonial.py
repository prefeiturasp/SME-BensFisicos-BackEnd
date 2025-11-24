from django.contrib import admin
from django.contrib import messages
from django.db.models import Q
from django.db import transaction
from bem_patrimonial.admins.actions.movimentacoe_duplicadas import (
    verificar_movimentacoes_duplicadas,
)
from bem_patrimonial.admins.forms.movimentacao_bem_patrimonial_form import (
    MovimentacaoBemPatrimonialForm,
)
from bem_patrimonial.models import (
    MovimentacaoBemPatrimonial,
    MovimentacaoBensItem,
)
from bem_patrimonial.emails import (
    envia_email_solicitacao_movimentacao_aceita,
    envia_email_solicitacao_movimentacao_rejeitada,
    envia_email_solicitacao_movimentacao_cancelada,
)
from bem_patrimonial import constants

from dados_comuns.libs.unidade_administrativa import uas_do_usuario
from dados_comuns.models import UnidadeAdministrativa
from bem_patrimonial.admins.inlines.inlines import MovimentacaoBensItemInline

UNIDADE_ADMINISTRATIVA_ORIGEM_AUTOCOMPLETE = "unidade_administrativa_origem"


def _bens_da_movimentacao(mov):
    """
    Helper: retorna queryset de bens da movimentação, já com select_related.
    """
    return mov.itens.select_related("bem").all()


def aprovar_solicitacao(modeladmin, request, queryset):
    for mov in queryset:
        if mov.aceita:
            messages.add_message(
                request,
                messages.WARNING,
                f"Movimentação #{mov.pk} já foi aprovada anteriormente.",
            )
            continue

        if mov.rejeitada:
            messages.add_message(
                request,
                messages.WARNING,
                f"Movimentação #{mov.pk} já foi rejeitada anteriormente.",
            )
            continue

        if not mov.unidade_administrativa_origem.is_ativa:
            messages.add_message(
                request,
                messages.ERROR,
                f"Movimentação #{mov.pk}: A unidade de origem "
                f"'{mov.unidade_administrativa_origem.nome}' está inativa. "
                "Não é possível aprovar movimentações de unidades inativas.",
            )
            continue

        if not mov.unidade_administrativa_destino.is_ativa:
            messages.add_message(
                request,
                messages.ERROR,
                f"Movimentação #{mov.pk}: A unidade de destino "
                f"'{mov.unidade_administrativa_destino.nome}' está inativa. "
                "Não é possível aprovar movimentações para unidades inativas.",
            )
            continue

        if mov.cancelada:
            messages.add_message(
                request,
                messages.ERROR,
                f"Movimentação #{mov.pk} foi cancelada e não pode ser aprovada.",
            )
            continue

        if request.user.is_operador_inventario:
            if (
                mov.unidade_administrativa_destino
                != request.user.unidade_administrativa
            ):
                messages.add_message(
                    request,
                    messages.ERROR,
                    f"Movimentação #{mov.pk}: Apenas operadores da unidade de destino "
                    "podem aprovar esta movimentação.",
                )
                continue
            if mov.solicitado_por_id == request.user.pk:
                messages.add_message(
                    request,
                    messages.WARNING,
                    f"Movimentação #{mov.pk}: Você não pode aprovar sua própria solicitação.",
                )
                continue

        bens_itens = _bens_da_movimentacao(mov)

        if not bens_itens.exists():
            messages.add_message(
                request,
                messages.ERROR,
                f"Movimentação #{mov.pk} não possui bens associados.",
            )
            continue

        with transaction.atomic():
            for item in bens_itens:
                bem = item.bem
                bem.unidade_administrativa = mov.unidade_administrativa_destino
                bem.status = constants.APROVADO
                bem.save()

                if mov.solicitado_por and mov.solicitado_por.email:
                    envia_email_solicitacao_movimentacao_aceita(
                        bem, mov.solicitado_por.email
                    )

            mov.status = constants.ACEITA
            mov.aprovado_por = request.user
            mov.save()

        messages.add_message(
            request,
            messages.SUCCESS,
            f"Movimentação #{mov.pk} aprovada com sucesso. Bens desbloqueados.",
        )


aprovar_solicitacao.short_description = "Aprovar movimentação selecionada"


def rejeitar_solicitacao(modeladmin, request, queryset):
    for mov in queryset:
        if mov.rejeitada:
            messages.add_message(
                request,
                messages.WARNING,
                f"Movimentação #{mov.pk} já foi rejeitada anteriormente.",
            )
            continue

        if mov.aceita:
            messages.add_message(
                request,
                messages.WARNING,
                f"Movimentação #{mov.pk} já foi aprovada anteriormente.",
            )
            continue

        if not mov.unidade_administrativa_origem.is_ativa:
            messages.add_message(
                request,
                messages.ERROR,
                f"Movimentação #{mov.pk}: A unidade de origem "
                f"'{mov.unidade_administrativa_origem.nome}' está inativa. "
                "Não é possível rejeitar movimentações de unidades inativas.",
            )
            continue

        if not mov.unidade_administrativa_destino.is_ativa:
            messages.add_message(
                request,
                messages.ERROR,
                f"Movimentação #{mov.pk}: A unidade de destino "
                f"'{mov.unidade_administrativa_destino.nome}' está inativa. "
                "Não é possível rejeitar movimentações para unidades inativas.",
            )
            continue

        if mov.cancelada:
            messages.add_message(
                request,
                messages.ERROR,
                f"Movimentação #{mov.pk} foi cancelada e não pode ser rejeitada.",
            )
            continue

        if request.user.is_operador_inventario:
            if (
                mov.unidade_administrativa_destino
                != request.user.unidade_administrativa
            ):
                messages.add_message(
                    request,
                    messages.ERROR,
                    f"Movimentação #{mov.pk}: Apenas operadores da unidade de destino "
                    "podem rejeitar esta movimentação.",
                )
                continue
            if mov.solicitado_por_id == request.user.pk:
                messages.add_message(
                    request,
                    messages.WARNING,
                    f"Movimentação #{mov.pk}: Você não pode rejeitar sua própria solicitação.",
                )
                continue

        bens_itens = _bens_da_movimentacao(mov)

        if not bens_itens.exists():
            messages.add_message(
                request,
                messages.ERROR,
                f"Movimentação #{mov.pk} não possui bens associados.",
            )
            continue

        with transaction.atomic():
            mov.status = constants.REJEITADA
            mov.rejeitado_por = request.user
            mov.save()

            for item in bens_itens:
                bem = item.bem
                bem.status = constants.APROVADO
                bem.save()

                if mov.solicitado_por and mov.solicitado_por.email:
                    envia_email_solicitacao_movimentacao_rejeitada(
                        bem, mov.solicitado_por.email
                    )

        messages.add_message(
            request,
            messages.SUCCESS,
            f"Movimentação #{mov.pk} rejeitada com sucesso. Bens desbloqueados.",
        )


rejeitar_solicitacao.short_description = "Rejeitar movimentação selecionada"


def cancelar_solicitacao(modeladmin, request, queryset):
    for mov in queryset:
        if mov.cancelada:
            messages.add_message(
                request,
                messages.WARNING,
                f"Movimentação #{mov.pk} já foi cancelada anteriormente.",
            )
            continue

        if mov.aceita:
            messages.add_message(
                request,
                messages.WARNING,
                f"Movimentação #{mov.pk} já foi aprovada e não pode ser cancelada.",
            )
            continue

        if mov.rejeitada:
            messages.add_message(
                request,
                messages.WARNING,
                f"Movimentação #{mov.pk} já foi rejeitada e não pode ser cancelada.",
            )
            continue

        if mov.status != constants.ENVIADA:
            messages.add_message(
                request,
                messages.ERROR,
                f"Movimentação #{mov.pk}: Apenas movimentações pendentes podem ser canceladas.",
            )
            continue

        if (
            request.user.is_operador_inventario
            and not request.user.is_gestor_patrimonio
        ):
            if mov.solicitado_por_id != request.user.pk:
                messages.add_message(
                    request,
                    messages.ERROR,
                    f"Movimentação #{mov.pk}: Você só pode cancelar movimentações criadas por você.",
                )
                continue

        bens_itens = _bens_da_movimentacao(mov)

        with transaction.atomic():
            mov.status = constants.CANCELADA
            mov.cancelado_por = request.user
            mov.save()

            for item in bens_itens:
                bem = item.bem
                bem.status = constants.APROVADO
                bem.save()

                if mov.solicitado_por and mov.solicitado_por.email:
                    envia_email_solicitacao_movimentacao_cancelada(
                        bem, request.user, mov.solicitado_por.email
                    )

        messages.add_message(
            request,
            messages.SUCCESS,
            f"Movimentação #{mov.pk} cancelada com sucesso. Bens desbloqueados.",
        )


cancelar_solicitacao.short_description = "Cancelar movimentação selecionada"


class MovimentacaoBemPatrimonialAdmin(admin.ModelAdmin):
    model = MovimentacaoBemPatrimonial

    list_display = (
        "id",
        "status",
        "unidade_administrativa_origem",
        "unidade_administrativa_destino",
        "solicitado_por",
        "atualizado_em",
    )

    autocomplete_fields = (
        "unidade_administrativa_origem",
        "unidade_administrativa_destino",
    )

    readonly_fields = (
        "solicitado_por",
        "aprovado_por",
        "rejeitado_por",
        "cancelado_por",
        "status",
        "numero_cimbpm",
        "get_documento_cimbpm_link",
    )

    list_filter = ("status",)
    actions = [
        aprovar_solicitacao,
        rejeitar_solicitacao,
        cancelar_solicitacao,
        verificar_movimentacoes_duplicadas,
    ]

    form = MovimentacaoBemPatrimonialForm
    inlines = [MovimentacaoBensItemInline]

    class Media:
        js = (
            "js/bem_patrimonial/prevenir_duplo_submit.js",
            "admin/movimentacao_filtra_bens_por_ua.js",
        )
        css = {"all": ("css/prevenir_duplo_submit.css", "css/custom_inline.css")}

    def get_fields(self, request, obj=None):
        base_fields = [
            "unidade_administrativa_origem",
            "unidade_administrativa_destino",
            "observacao",
        ]

        if obj is not None:
            return [
                "status",
                "numero_cimbpm",
                "get_documento_cimbpm_link",
                "solicitado_por",
                "aprovado_por",
                "rejeitado_por",
                "cancelado_por",
                *base_fields,
            ]

        return base_fields

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return self.readonly_fields

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.request = request

        if obj is None:
            uas = uas_do_usuario(request.user)
            uas = uas.filter(status=UnidadeAdministrativa.ATIVA)

            if uas.count() == 1:
                ua = uas.first()
                if (
                    hasattr(form, "base_fields")
                    and UNIDADE_ADMINISTRATIVA_ORIGEM_AUTOCOMPLETE in form.base_fields
                ):
                    form.base_fields[
                        UNIDADE_ADMINISTRATIVA_ORIGEM_AUTOCOMPLETE
                    ].initial = ua.pk

        return form

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_operador_inventario or (
            request.user.is_gestor_patrimonio and request.user.unidade_administrativa
        ):
            return qs.filter(
                Q(unidade_administrativa_origem=request.user.unidade_administrativa)
                | Q(unidade_administrativa_destino=request.user.unidade_administrativa)
            )
        return qs

    def save_model(self, request, obj, form, change):
        if obj.id is None:
            obj.solicitado_por = request.user
        super().save_model(request, obj, form, change)

    def get_documento_cimbpm_link(self, obj):
        if obj and obj.numero_cimbpm:
            from django.utils.html import format_html
            from django.urls import reverse

            url_protegida = reverse("download_documento_cimbpm", kwargs={"pk": obj.pk})

            return format_html(
                '<a href="{}" target="_blank">📄 Baixar Documento CIMBPM</a>',
                url_protegida,
            )
        return "Número CIMBPM não gerado"

    get_documento_cimbpm_link.short_description = "Documento CIMBPM"

    def get_actions(self, request):
        actions = super().get_actions(request)
        return actions

    def response_action(self, request, queryset):

        action_name = request.POST.get("action")

        if action_name == "verificar_movimentacoes_duplicadas":
            changelist = self.get_changelist_instance(request)
            qs = changelist.get_queryset(request)
            return verificar_movimentacoes_duplicadas(self, request, qs)

        return super().response_action(request, queryset)

    def get_inline_formsets(self, request, formsets, inline_instances, obj=None):
        inline_formsets = super().get_inline_formsets(
            request, formsets, inline_instances, obj
        )

        if obj is not None:
            for formset in inline_formsets:
                formset.can_add = False
        return inline_formsets
