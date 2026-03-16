from django.urls import path
from django.contrib import admin, messages
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError
from django.forms import DateInput
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect
from django.utils.formats import date_format
from rangefilter.filters import DateRangeFilter

from bem_patrimonial.models import (
    BaixaFisicaBemPatrimonial,
    BaixaFisicaBensItem,
)
from bem_patrimonial.emails import (
    envia_email_baixa_fisica_solicitada,
    envia_email_baixa_fisica_aprovada,
    envia_email_baixa_fisica_cancelada,
)
from bem_patrimonial import constants
from bem_patrimonial.nbbpm import http_response_nbbpm
from dados_comuns.escopo import (
    filtrar_queryset_por_escopo,
    filtrar_ua_origem_por_escopo,
    usuario_e_super_admin,
)
from dados_comuns.models import UnidadeAdministrativa


class BaixaFisicaBensItemInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        total_validos = 0

        for form in self.forms:
            if not hasattr(form, "cleaned_data"):
                continue

            if form.cleaned_data.get("DELETE"):
                continue

            bem = form.cleaned_data.get("bem") or getattr(form.instance, "bem", None)

            if not bem:
                continue

            total_validos += 1

        if total_validos == 0:
            raise ValidationError(
                "Informe ao menos um bem para realizar a Baixa Física."
            )


class BaixaFisicaBensItemInline(admin.TabularInline):
    model = BaixaFisicaBensItem
    extra = 0
    autocomplete_fields = ("bem",)
    formset = BaixaFisicaBensItemInlineFormSet

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        class ScopedForm(form):
            def __init__(self_inner, *a, **kw):
                super().__init__(*a, **kw)

                if "unidade_administrativa_origem" in self_inner.fields:
                    fld = self_inner.fields["unidade_administrativa_origem"]

                    base_qs = UnidadeAdministrativa.objects.filter(
                        status=UnidadeAdministrativa.ATIVA
                    )

                    fld.queryset = filtrar_ua_origem_por_escopo(request.user, base_qs)

                    ua_user = getattr(request.user, "unidade_administrativa", None)
                    if (
                        ua_user
                        and ua_user.is_ativa
                        and not usuario_e_super_admin(request.user)
                    ):
                        fld.initial = ua_user.pk
                        fld.disabled = True

            def clean(self_inner):
                cleaned = super().clean()
                ua_origem = cleaned.get("unidade_administrativa_origem")

                ua_user = getattr(request.user, "unidade_administrativa", None)
                if (
                    ua_user
                    and ua_user.is_ativa
                    and not usuario_e_super_admin(request.user)
                ):
                    cleaned["unidade_administrativa_origem"] = ua_user
                    ua_origem = ua_user

                if not ua_origem:
                    raise ValidationError(
                        {
                            "unidade_administrativa_origem": "Unidade administrativa de origem é obrigatória."
                        }
                    )

                if ua_origem.status != UnidadeAdministrativa.ATIVA:
                    raise ValidationError(
                        {
                            "unidade_administrativa_origem": "A unidade de origem está inativa."
                        }
                    )

                allowed = filtrar_ua_origem_por_escopo(
                    request.user,
                    UnidadeAdministrativa.objects.filter(
                        status=UnidadeAdministrativa.ATIVA
                    ),
                )
                if not allowed.filter(pk=ua_origem.pk).exists():
                    raise ValidationError(
                        {
                            "unidade_administrativa_origem": "Você não tem permissão para usar esta Unidade Administrativa como origem."  # noqa: E501
                        }
                    )

                return cleaned

        return ScopedForm

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)

        bem_field = formset.form.base_fields.get("bem")
        if bem_field:
            widget = bem_field.widget
            widget.can_add_related = False
            widget.can_change_related = False
            widget.can_view_related = False
            widget.can_delete_related = False

        return formset

    def has_add_permission(self, request, obj):

        if obj is None:
            return True

        return obj.status == constants.AGUARDANDO_ENVIO

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return False
        return obj.status == constants.AGUARDANDO_ENVIO

    def get_max_num(self, request, obj=None):

        if obj is not None and obj.status != constants.AGUARDANDO_ENVIO:
            return 0
        return super().get_max_num(request, obj)

    def get_readonly_fields(self, request, obj=None):

        if obj and obj.status != constants.AGUARDANDO_ENVIO:
            return ("bem",)
        return ()


class BaixaFisicaBemPatrimonialAdmin(admin.ModelAdmin):
    list_display = (
        "numero_nbbpm",
        "unidade_administrativa_origem",
        "status",
        "criado_por",
        "aprovado_por",
        "data_aprovacao_formatada",
    )
    list_display_links = ("numero_nbbpm",)
    list_filter = ("status", 
                   ("data_aprovacao", DateRangeFilter),
                   )
    search_fields = (
        "numero_processo_baixa",
        "numero_nbbpm",
        "unidade_administrativa_origem__nome",
        "unidade_administrativa_origem__sigla",
        "unidade_administrativa_origem__codigo",
        "criado_por__username",
        "aprovado_por__username",
        "itens__bem__numero_patrimonial",
        "itens__bem__nome",
    )

    def get_search_results(self, request, queryset, search_term):
        queryset, _ = super().get_search_results(
            request, queryset, search_term
        )
        return queryset.distinct(), True

    def data_aprovacao_formatada(self, obj):
        if obj.data_aprovacao:
            return date_format(obj.data_aprovacao, "d \\d\\e F \\d\\e Y")
        return "-"

    data_aprovacao_formatada.short_description = "Data da aprovação"
    data_aprovacao_formatada.admin_order_field = "data_aprovacao"

    inlines = [BaixaFisicaBensItemInline]
    autocomplete_fields = ("unidade_administrativa_origem",)
    change_form_template = "admin/bem_patrimonial/baixa_fisica/change_form.html"

    class Media:
        js = ("admin/baixa_fisica_autocomplete.js")
        css = {
            "all": (
                "css/hide_crud_icons.css",
                "css/baixa_fisica_inline.css",
                "css/custom_baixa_fisica.css",
            )
        }

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return (
                "unidade_administrativa_origem",
                "numero_processo_baixa",
                "status",
                "criado_por",
                "data_criacao",
                "aprovado_por",
                "data_aprovacao",
                "data_baixa",
            )
        return ()

    def get_fieldsets(self, request, obj=None):
        campos_basicos = (
            "unidade_administrativa_origem",
            "numero_processo_baixa",
            "data_baixa",
        )

        if obj:
            campos = campos_basicos + (
                "criado_por",
                "data_criacao",
                "aprovado_por",
                "data_aprovacao",
                "status",
            )
        else:
            campos = campos_basicos

        return (
            (
                "Realizar Baixa Física do Bem Patrimonial",
                {"fields": campos},
            ),
        )

    def save_model(self, request, obj, form, change):
        if not change or not obj.criado_por_id:
            obj.criado_por = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        """
        Depois de salvar os inlines, ajusta o status dos bens
        conforme inclusão/remoção de itens, mas APENAS quando
        a baixa está em status 'aguardando envio' (SOLICITADA).
        """
        super().save_related(request, form, formsets, change)

        baixa = form.instance

        if baixa.status != constants.AGUARDANDO_ENVIO:
            return

        for formset in formsets:

            if getattr(formset, "model", None) is not BaixaFisicaBensItem:
                continue

            for item in formset.deleted_objects:
                bem = item.bem
                if bem.status == constants.BAIXA_FISICA_AGUARDANDO_APROVACAO:
                    bem.status = constants.APROVADO
                    bem.save(update_fields=["status"])

            for item in getattr(formset, "new_objects", []):
                bem = item.bem
                if bem.status != constants.BAIXA_FISICA_AGUARDANDO_APROVACAO:
                    bem.status = constants.BAIXA_FISICA_AGUARDANDO_APROVACAO
                    bem.save(update_fields=["status"])

    def has_view_permission(self, request, obj=None):
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            user.is_gestor_patrimonio
            or user.is_operador_inventario
            or user.is_superuser
        )

    def has_add_permission(self, request):
        return self.has_view_permission(request)

    def has_change_permission(self, request, obj=None):

        return self.has_view_permission(request, obj)

    def has_delete_permission(self, request, obj=None):

        return False

    def get_queryset(self, request):
        qs = (
            super()
            .get_queryset(request)
            .select_related("unidade_administrativa_origem", "criado_por")
        )

        return filtrar_queryset_por_escopo(
            usuario=request.user,
            queryset=qs,
            campo_ua="unidade_administrativa_origem",
        )

    def changelist_view(self, request, extra_context=None):
        user = request.user
        ua = getattr(user, "unidade_administrativa", None)

        if user.is_operador_inventario and not ua:
            messages.warning(
                request,
                "Como operador você deve estár vinculado a uma unidade administrativa",
            )

        return super().changelist_view(request, extra_context=extra_context)

    actions = ["acao_enviar_baixa", "acao_aprovar_baixa", "acao_cancelar_baixa"]

    def get_actions(self, request):
        actions = super().get_actions(request)

        actions.pop("delete_selected", None)

        if not (request.user.is_gestor_patrimonio or request.user.is_superuser):
            actions.pop("acao_aprovar_baixa", None)
            actions.pop("acao_cancelar_baixa", None)

        return actions

    def acao_enviar_baixa(self, request, queryset):

        baixas_permitidas = queryset.filter(status=constants.AGUARDANDO_ENVIO)
        baixas_invalidas = queryset.exclude(status=constants.AGUARDANDO_ENVIO)

        if baixas_invalidas.exists():
            lista_invalidas = ", ".join(
                f"#{b.pk} (status={b.get_status_display()})" for b in baixas_invalidas
            )
            self.message_user(
                request,
                (
                    "As seguintes Baixas Físicas não podem ser solicitadas, "
                    "pois não estão com status 'Aguardando envio': "
                    f"{lista_invalidas}"
                ),
                level=messages.ERROR,
            )

        if not baixas_permitidas.exists():
            self.message_user(
                request,
                "Nenhuma das Baixas Físicas selecionadas pode ser solicitada.",
                level=messages.WARNING,
            )
            return

        solicitadas = 0
        for baixa in baixas_permitidas:
            baixa.enviar_solicitacao()
            envia_email_baixa_fisica_solicitada(baixa)
            solicitadas += 1

        self.message_user(
            request,
            f"{solicitadas} Baixa(s) Física(s) solicitada(s) para aprovação.",
            level=messages.SUCCESS,
        )

    acao_enviar_baixa.short_description = "Solicitar Baixa Física selecionadas"

    def acao_aprovar_baixa(self, request, queryset):
        if not (request.user.is_gestor_patrimonio or request.user.is_superuser):
            self.message_user(
                request,
                "Apenas Gestor de Patrimônio pode aprovar Baixa Física.",
                level=messages.ERROR,
            )
            return

        baixas_solicitadas = queryset.filter(status=constants.SOLICITADA)
        baixas_nao_solicitadas = queryset.exclude(status=constants.SOLICITADA)

        if baixas_nao_solicitadas.exists():
            lista_nao_aprovaveis = ", ".join(
                f"#{b.pk} (status={b.get_status_display()})"
                for b in baixas_nao_solicitadas
            )
            self.message_user(
                request,
                (
                    "As seguintes Baixas Físicas não podem ser aprovadas, "
                    "pois não estão com status 'Solicitada': "
                    f"{lista_nao_aprovaveis}"
                ),
                level=messages.ERROR,
            )

        if not baixas_solicitadas.exists():
            self.message_user(
                request,
                "Nenhuma das Baixas Físicas selecionadas está com status 'Solicitada'. Nada foi aprovado.",
                level=messages.WARNING,
            )
            return

        aprovadas = 0
        for baixa in baixas_solicitadas:
            baixa.aprovar(usuario_aprovador=request.user)
            envia_email_baixa_fisica_aprovada(baixa)
            aprovadas += 1

        if aprovadas:
            self.message_user(
                request,
                f"{aprovadas} Baixa(s) Física(s) aprovada(s) com sucesso.",
                level=messages.SUCCESS,
            )

    acao_aprovar_baixa.short_description = "Aprovar Baixa Física selecionadas"

    def acao_cancelar_baixa(self, request, queryset):
        if not (request.user.is_gestor_patrimonio or request.user.is_superuser):
            self.message_user(
                request,
                "Apenas Gestor de Patrimônio pode recusar Baixa Física.",
                level=messages.ERROR,
            )
            return

        baixas_aceitas = queryset.filter(status=constants.ACEITA)

        if baixas_aceitas.exists():
            lista_aceitas = ", ".join(
                f"#{b.pk} (proc. {b.numero_processo_baixa})" for b in baixas_aceitas
            )
            self.message_user(
                request,
                (
                    "As seguintes Baixas Físicas já estão aprovadas e "
                    "não podem ser recusadas: "
                    f"{lista_aceitas}"
                ),
                level=messages.ERROR,
            )

        baixas_recusaveis = queryset.filter(
            status__in=[constants.AGUARDANDO_ENVIO, constants.SOLICITADA]
        )

        if not baixas_recusaveis.exists():
            self.message_user(
                request,
                (
                    "Nenhuma das Baixas Físicas selecionadas está em status "
                    "'Aguardando envio' ou 'solicitada'. Nada foi recusado."
                ),
                level=messages.WARNING,
            )
            return

        lista_recusaveis = ", ".join(
            f"#{b.pk} (proc. {b.numero_processo_baixa}, status={b.get_status_display()})"
            for b in baixas_recusaveis
        )
        self.message_user(
            request,
            ("Serão recusadas as seguintes Baixas Físicas: " f"{lista_recusaveis}"),
            level=messages.INFO,
        )

        canceladas = 0
        for baixa in baixas_recusaveis:

            for item in baixa.itens.select_related("bem"):
                bem = item.bem
                if bem.status == constants.BAIXA_FISICA_AGUARDANDO_APROVACAO:
                    bem.status = constants.APROVADO
                    bem.save(update_fields=["status"])

            baixa.status = constants.RECUSADA
            baixa.save(update_fields=["status"])
            canceladas += 1

            envia_email_baixa_fisica_cancelada(baixa, request.user)

        if canceladas:
            self.message_user(
                request,
                f"{canceladas} Baixa(s) Física(s) cancelada(s) com sucesso.",
                level=messages.SUCCESS,
            )

    acao_cancelar_baixa.short_description = "Recusar Baixa Física selecionadas"

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "data_baixa":
            hoje = timezone.localdate()
            kwargs["widget"] = DateInput(
                attrs={
                    "type": "date",
                    "max": hoje.strftime("%Y-%m-%d"),
                }
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:baixa_id>/nbbpm/",
                self.admin_site.admin_view(self.baixar_nbbpm),
                name="baixafisica_nbbpm",
            ),
        ]
        return custom_urls + urls

    def baixar_nbbpm(self, request, baixa_id):
        baixa = get_object_or_404(BaixaFisicaBemPatrimonial, pk=baixa_id)

        if baixa.status != constants.ACEITA:
            messages.error(
                request,
                "A Nota NBBPM só pode ser gerada para Baixas Físicas aprovadas.",
            )
            return redirect(f"../{baixa_id}/change/")

        return http_response_nbbpm(baixa)
