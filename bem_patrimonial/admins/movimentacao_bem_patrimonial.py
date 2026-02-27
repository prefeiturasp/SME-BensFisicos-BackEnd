from django.contrib import admin
from django.contrib import messages
from django.db import transaction
from bem_patrimonial.admins.actions.movimentacoe_duplicadas import (
    verificar_movimentacoes_duplicadas,
)
from bem_patrimonial.admins.forms.movimentacao_bem_patrimonial_form import (
    MovimentacaoBemPatrimonialForm,
)
from bem_patrimonial.admins.filters.movimentacao_filters import (
    MovimentacaoAtrasadaFilter,
)
from bem_patrimonial.models import (
    MovimentacaoBemPatrimonial,
)
from bem_patrimonial.emails import (
    envia_email_solicitacao_movimentacao_aceita,
    envia_email_solicitacao_movimentacao_rejeitada,
    envia_email_solicitacao_movimentacao_cancelada,
)
from bem_patrimonial import constants

from bem_patrimonial.admins.inlines.inlines import MovimentacaoBensItemInline

from dados_comuns.escopo import (
    filtrar_queryset_movimentacao_por_escopo,
)


UNIDADE_ADMINISTRATIVA_ORIGEM_AUTOCOMPLETE = "unidade_administrativa_origem"


def _bens_da_movimentacao(mov):
    """
    Helper: retorna queryset de bens da movimentação, já com select_related.
    """
    return mov.itens.select_related("bem").all()


def _mensagem_mov_origem_destino_inativas(mov, request, acao_verb):
    if not mov.unidade_administrativa_origem.is_ativa:
        messages.add_message(
            request,
            messages.ERROR,
            f"Movimentação #{mov.pk}: A unidade de origem "
            f"'{mov.unidade_administrativa_origem.nome}' está inativa. "
            f"Não é possível {acao_verb} movimentações de unidades inativas.",
        )
        return True
    if not mov.unidade_administrativa_destino.is_ativa:
        messages.add_message(
            request,
            messages.ERROR,
            f"Movimentação #{mov.pk}: A unidade de destino "
            f"'{mov.unidade_administrativa_destino.nome}' está inativa. "
            f"Não é possível {acao_verb} movimentações para unidades inativas.",
        )
        return True
    return False


def _check_operador_destino_aprovacao(mov, request):
    if not request.user.is_operador_inventario:
        return False
    if mov.unidade_administrativa_destino != request.user.unidade_administrativa:
        messages.add_message(
            request,
            messages.ERROR,
            f"Movimentação #{mov.pk}: Apenas operadores da unidade de destino "
            "podem aprovar esta movimentação.",
        )
        return True
    if mov.solicitado_por_id == request.user.pk:
        messages.add_message(
            request,
            messages.WARNING,
            f"Movimentação #{mov.pk}: Você não pode aprovar sua própria solicitação.",
        )
        return True
    return False


def _check_operador_destino_rejeicao(mov, request):
    if not request.user.is_operador_inventario:
        return False
    if mov.unidade_administrativa_destino != request.user.unidade_administrativa:
        messages.add_message(
            request,
            messages.ERROR,
            f"Movimentação #{mov.pk}: Apenas operadores da unidade de destino "
            "podem rejeitar esta movimentação.",
        )
        return True
    if mov.solicitado_por_id == request.user.pk:
        messages.add_message(
            request,
            messages.WARNING,
            f"Movimentação #{mov.pk}: Você não pode rejeitar sua própria solicitação.",
        )
        return True
    return False


def _bloqueio_se_algum(request, mov, checks):
    """Retorna True se algum check (condição, nível) retornar True e adicionar mensagem."""
    for condicao, msg, nivel in checks:
        if condicao:
            messages.add_message(request, nivel, msg.format(mov=mov))
            return True
    return False


def _nao_pode_aprovar(mov, request):
    checks = [
        (mov.aceita, "Movimentação #{mov.pk} já foi aprovada anteriormente.", messages.WARNING),
        (mov.rejeitada, "Movimentação #{mov.pk} já foi rejeitada anteriormente.", messages.WARNING),
        (mov.cancelada, "Movimentação #{mov.pk} foi cancelada e não pode ser aprovada.", messages.ERROR),
    ]
    if _bloqueio_se_algum(request, mov, checks):
        return True
    if _mensagem_mov_origem_destino_inativas(mov, request, "aprovar"):
        return True
    if _check_operador_destino_aprovacao(mov, request):
        return True
    return False


def aprovar_solicitacao(modeladmin, request, queryset):
    for mov in queryset:
        if _nao_pode_aprovar(mov, request):
            continue
        bens_itens = _bens_da_movimentacao(mov)
        if not bens_itens.exists():
            messages.add_message(
                request, messages.ERROR,
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
            request, messages.SUCCESS,
            f"Movimentação #{mov.pk} aprovada com sucesso. Bens desbloqueados.",
        )


aprovar_solicitacao.short_description = "Aprovar movimentação selecionada"


def _nao_pode_rejeitar(mov, request):
    checks = [
        (mov.rejeitada, "Movimentação #{mov.pk} já foi rejeitada anteriormente.", messages.WARNING),
        (mov.aceita, "Movimentação #{mov.pk} já foi aprovada anteriormente.", messages.WARNING),
        (mov.cancelada, "Movimentação #{mov.pk} foi cancelada e não pode ser rejeitada.", messages.ERROR),
    ]
    if _bloqueio_se_algum(request, mov, checks):
        return True
    if _mensagem_mov_origem_destino_inativas(mov, request, "rejeitar"):
        return True
    if _check_operador_destino_rejeicao(mov, request):
        return True
    return False


def rejeitar_solicitacao(modeladmin, request, queryset):
    for mov in queryset:
        if _nao_pode_rejeitar(mov, request):
            continue
        bens_itens = _bens_da_movimentacao(mov)
        if not bens_itens.exists():
            messages.add_message(
                request, messages.ERROR,
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
            request, messages.SUCCESS,
            f"Movimentação #{mov.pk} rejeitada com sucesso. Bens desbloqueados.",
        )


rejeitar_solicitacao.short_description = "Rejeitar movimentação selecionada"


def _nao_pode_cancelar(mov, request):
    checks = [
        (mov.cancelada, "Movimentação #{mov.pk} já foi cancelada anteriormente.", messages.WARNING),
        (mov.aceita, "Movimentação #{mov.pk} já foi aprovada e não pode ser cancelada.", messages.WARNING),
        (mov.rejeitada, "Movimentação #{mov.pk} já foi rejeitada e não pode ser cancelada.", messages.WARNING),
        (mov.status != constants.ENVIADA, "Movimentação #{mov.pk}: Apenas movimentações pendentes podem ser canceladas.", messages.ERROR),
        (
            request.user.is_operador_inventario
            and not request.user.is_gestor_patrimonio
            and mov.solicitado_por_id != request.user.pk,
            "Movimentação #{mov.pk}: Você só pode cancelar movimentações criadas por você.",
            messages.ERROR,
        ),
    ]
    return _bloqueio_se_algum(request, mov, checks)


def cancelar_solicitacao(modeladmin, request, queryset):
    for mov in queryset:
        if _nao_pode_cancelar(mov, request):
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
            request, messages.SUCCESS,
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

    search_fields = (
        "numero_cimbpm",
        "unidade_administrativa_origem__codigo",
        "unidade_administrativa_origem__nome",
        "unidade_administrativa_origem__sigla",
        "unidade_administrativa_destino__codigo",
        "unidade_administrativa_destino__nome",
        "unidade_administrativa_destino__sigla",
        "unidade_administrativa_origem__unidade_orcamentaria__codigo",
        "unidade_administrativa_origem__unidade_orcamentaria__nome",
        "unidade_administrativa_destino__unidade_orcamentaria__codigo",
        "unidade_administrativa_destino__unidade_orcamentaria__nome",
        "itens__bem__numero_patrimonial",
        "itens__bem__nome",
        "itens__bem__descricao",
        "itens__bem__marca",
        "itens__bem__modelo",
        "itens__bem__localizacao",
        "itens__bem__numero_processo",
        "bem_patrimonial__numero_patrimonial",
        "bem_patrimonial__nome",
        "bem_patrimonial__descricao",
        "bem_patrimonial__marca",
        "bem_patrimonial__modelo",
        "bem_patrimonial__localizacao",
        "bem_patrimonial__numero_processo",
    )

    search_help_text = (
        "Pesquise por número patrimonial, nome, descrição, marca, modelo, localização e "
        "número de processo do bem, código/nome/sigla da UA (origem/destino), número CIMBPM e "
        "Unidade Orçamentária."
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
        "unidade_administrativa_origem",
        "unidade_administrativa_destino",
    )

    list_filter = ("status", MovimentacaoAtrasadaFilter)
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
        css = {
            "all": (
                "css/prevenir_duplo_submit.css",
                "css/custom_inline.css",
                "css/hide_crud_icons.css",
            )
        }

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
        form_class = super().get_form(request, obj, **kwargs)

        class RequestForm(form_class):
            def __init__(self_inner, *a, **kw):
                super().__init__(*a, **kw)
                self_inner.request = request

                if obj is None:
                    ua_user = getattr(request.user, "unidade_administrativa", None)
                    if (
                        ua_user
                        and ua_user.is_ativa
                        and hasattr(self_inner, "base_fields")
                        and UNIDADE_ADMINISTRATIVA_ORIGEM_AUTOCOMPLETE in self_inner.base_fields
                    ):
                        self_inner.base_fields[
                            UNIDADE_ADMINISTRATIVA_ORIGEM_AUTOCOMPLETE
                        ].initial = ua_user.pk

        return RequestForm

    def get_queryset(self, request):
        qs = (
            super()
            .get_queryset(request)
            .select_related(
                "unidade_administrativa_origem",
                "unidade_administrativa_destino",
                "solicitado_por",
                "aprovado_por",
                "rejeitado_por",
                "cancelado_por",
            )
        )
        return filtrar_queryset_movimentacao_por_escopo(request.user, qs)

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
                formset.can_delete = False
                for form in formset.forms:
                    for field in form.fields.values():
                        field.disabled = True
        return inline_formsets
