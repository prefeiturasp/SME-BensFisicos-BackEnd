from django.contrib import admin
from django.contrib import messages
from django.db.models import Q
from django.db import transaction
from bem_patrimonial.admins.forms.movimentacao_bem_patrimonial_form import (
    MovimentacaoBemPatrimonialForm,
)
from bem_patrimonial.models import MovimentacaoBemPatrimonial
from bem_patrimonial.emails import (
    envia_email_solicitacao_movimentacao_aceita,
    envia_email_solicitacao_movimentacao_rejeitada,
)

from dados_comuns.libs.unidade_administrativa import uas_do_usuario

UNIDADE_ADMINISTRATIVA_ORIGEM_AUTOCOMPLETE = "unidade_administrativa_origem"


def aprovar_solicitacao(modeladmin, request, queryset):
    for item in queryset:
        if item.aceita:
            messages.add_message(
                request,
                messages.WARNING,
                f"Movimentação #{item.pk} já foi aprovada anteriormente.",
            )
            continue

        if item.rejeitada:
            messages.add_message(
                request,
                messages.WARNING,
                f"Movimentação #{item.pk} já foi rejeitada anteriormente.",
            )
            continue

        if request.user.is_operador_inventario:
            if (
                item.unidade_administrativa_destino
                != request.user.unidade_administrativa
            ):
                messages.add_message(
                    request,
                    messages.ERROR,
                    f"Movimentação #{item.pk}: Apenas operadores da unidade de destino podem aprovar esta movimentação.",
                )
                continue
            if item.solicitado_por.pk == request.user.pk:
                messages.add_message(
                    request,
                    messages.WARNING,
                    f"Movimentação #{item.pk}: Você não pode aprovar sua própria solicitação.",
                )
                continue

        item.aprovar_solicitacao(request.user)
        messages.add_message(
            request,
            messages.SUCCESS,
            f"Movimentação #{item.pk} aprovada com sucesso. Bem desbloqueado.",
        )
        envia_email_solicitacao_movimentacao_aceita(
            item.bem_patrimonial, item.solicitado_por.email
        )


aprovar_solicitacao.short_description = "Aprovar movimentação selecionada"


def rejeitar_solicitacao(modeladmin, request, queryset):
    for item in queryset:
        if item.rejeitada:
            messages.add_message(
                request,
                messages.WARNING,
                f"Movimentação #{item.pk} já foi rejeitada anteriormente.",
            )
            continue

        if item.aceita:
            messages.add_message(
                request,
                messages.WARNING,
                f"Movimentação #{item.pk} já foi aprovada anteriormente.",
            )
            continue

        if request.user.is_operador_inventario:
            if (
                item.unidade_administrativa_destino
                != request.user.unidade_administrativa
            ):
                messages.add_message(
                    request,
                    messages.ERROR,
                    f"Movimentação #{item.pk}: Apenas operadores da unidade de destino podem rejeitar esta movimentação.",
                )
                continue
            if item.solicitado_por.pk == request.user.pk:
                messages.add_message(
                    request,
                    messages.WARNING,
                    f"Movimentação #{item.pk}: Você não pode rejeitar sua própria solicitação.",
                )
                continue

        item.rejeitar_solicitacao(request.user)
        messages.add_message(
            request,
            messages.SUCCESS,
            f"Movimentação #{item.pk} rejeitada com sucesso. Bem desbloqueado.",
        )
        envia_email_solicitacao_movimentacao_rejeitada(
            item.bem_patrimonial, item.solicitado_por.email
        )


rejeitar_solicitacao.short_description = "Rejeitar movimentação selecionada"


class MovimentacaoBemPatrimonialAdmin(admin.ModelAdmin):
    model = MovimentacaoBemPatrimonial
    list_display = (
        "id",
        "status",
        "bem_patrimonial",
        "unidade_administrativa_origem",
        "unidade_administrativa_destino",
        "quantidade",
        "solicitado_por",
        "atualizado_em",
    )
    autocomplete_fields = (
        "bem_patrimonial",
        "unidade_administrativa_origem",
        "unidade_administrativa_destino",
    )

    readonly_fields = (
        "solicitado_por",
        "aprovado_por",
        "rejeitado_por",
        "status",
    )
    list_filter = ("status",)
    actions = [aprovar_solicitacao, rejeitar_solicitacao]

    form = MovimentacaoBemPatrimonialForm

    class Media:
        js = ("js/bem_patrimonial/prevenir_duplo_submit.js",)
        css = {"all": ("css/prevenir_duplo_submit.css",)}

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.request = request

        if obj is None:
            uas = uas_do_usuario(request.user)
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
        if request.user.is_operador_inventario:
            return MovimentacaoBemPatrimonial.objects.filter(
                Q(unidade_administrativa_origem=request.user.unidade_administrativa)
                | Q(unidade_administrativa_destino=request.user.unidade_administrativa)
            )
        return MovimentacaoBemPatrimonial.objects.all()

    def save_model(self, request, obj, form, change):
        if obj.id is None:
            # Proteção contra duplicação usando lock transacional
            with transaction.atomic():
                from bem_patrimonial.models import BemPatrimonial

                bem_locked = BemPatrimonial.objects.select_for_update().get(
                    pk=obj.bem_patrimonial.pk
                )

                if bem_locked.tem_movimentacao_pendente:
                    messages.add_message(
                        request,
                        messages.WARNING,
                        f"O bem '{bem_locked}' já possui uma movimentação pendente. Aguarde a conclusão antes de criar uma nova.",
                    )
                    return

                obj.solicitado_por = request.user
                super().save_model(request, obj, form, change)
        else:
            super().save_model(request, obj, form, change)
