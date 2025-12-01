from django.contrib import admin, messages
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError

from bem_patrimonial.models import (
    BaixaFisicaBemPatrimonial,
    BaixaFisicaBensItem,
)
from bem_patrimonial.emails import (
    envia_email_baixa_fisica_enviada,
    envia_email_baixa_fisica_aprovada,
    envia_email_baixa_fisica_cancelada,
)
from bem_patrimonial import constants


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
        "id",
        "unidade_administrativa_origem",
        "numero_processo_baixa",
        "status",
        "criado_por",
        "data_criacao",
        "aprovado_por",
        "data_aprovacao",
    )
    list_filter = ("status",)
    search_fields = (
        "numero_processo_baixa",
        "unidade_administrativa_origem__nome",
        "unidade_administrativa_origem__codigo",
    )

    inlines = [BaixaFisicaBensItemInline]
    autocomplete_fields = ("unidade_administrativa_origem",)

    class Media:
        js = ("admin/baixa_fisica_autocomplete.js",)
        css = {"all": ("css/hide_crud_icons.css", "css/baixa_fisica_inline.css")}

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
            )
        return ()

    def get_fieldsets(self, request, obj=None):
        campos_basicos = (
            "unidade_administrativa_origem",
            "numero_processo_baixa",
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
        a baixa está em status 'aguardando envio' (ENVIADA).
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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user

        ua = getattr(user, "unidade_administrativa", None)
        if ua:
            return qs.filter(unidade_administrativa_origem=ua)

        if user.is_gestor_patrimonio or user.is_superuser:
            return qs

        return qs.none()

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

        if not request.user.is_gestor_patrimonio:
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
                    "As seguintes Baixas Físicas não podem ser enviadas, "
                    "pois não estão com status 'Aguardando envio': "
                    f"{lista_invalidas}"
                ),
                level=messages.ERROR,
            )

        if not baixas_permitidas.exists():
            self.message_user(
                request,
                "Nenhuma das Baixas Físicas selecionadas pode ser enviada.",
                level=messages.WARNING,
            )
            return

        enviadas = 0
        for baixa in baixas_permitidas:
            baixa.enviar_solicitacao()
            envia_email_baixa_fisica_enviada(baixa)
            enviadas += 1

        self.message_user(
            request,
            f"{enviadas} Baixa(s) Física(s) enviada(s) para aprovação.",
            level=messages.SUCCESS,
        )

    acao_enviar_baixa.short_description = "Enviar Baixa Física selecionadas"

    def acao_aprovar_baixa(self, request, queryset):
        if not request.user.is_gestor_patrimonio:
            self.message_user(
                request,
                "Apenas Gestor de Patrimônio pode aprovar Baixa Física.",
                level=messages.ERROR,
            )
            return

        baixas_enviadas = queryset.filter(status=constants.ENVIADA)
        baixas_nao_enviadas = queryset.exclude(status=constants.ENVIADA)

        if baixas_nao_enviadas.exists():
            lista_nao_aprovaveis = ", ".join(
                f"#{b.pk} (status={b.get_status_display()})"
                for b in baixas_nao_enviadas
            )
            self.message_user(
                request,
                (
                    "As seguintes Baixas Físicas não podem ser aprovadas, "
                    "pois não estão com status 'Enviada': "
                    f"{lista_nao_aprovaveis}"
                ),
                level=messages.ERROR,
            )

        if not baixas_enviadas.exists():
            self.message_user(
                request,
                "Nenhuma das Baixas Físicas selecionadas está com status 'Enviada'. Nada foi aprovado.",
                level=messages.WARNING,
            )
            return

        aprovadas = 0
        for baixa in baixas_enviadas:
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
        if not request.user.is_gestor_patrimonio:
            self.message_user(
                request,
                "Apenas Gestor de Patrimônio pode cancelar Baixa Física.",
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
                    "não podem ser canceladas: "
                    f"{lista_aceitas}"
                ),
                level=messages.ERROR,
            )

        baixas_cancelaveis = queryset.filter(
            status__in=[constants.AGUARDANDO_ENVIO, constants.ENVIADA]
        )

        if not baixas_cancelaveis.exists():
            self.message_user(
                request,
                (
                    "Nenhuma das Baixas Físicas selecionadas está em status "
                    "'Aguardando envio' ou 'Enviada'. Nada foi cancelado."
                ),
                level=messages.WARNING,
            )
            return

        lista_cancelaveis = ", ".join(
            f"#{b.pk} (proc. {b.numero_processo_baixa}, status={b.get_status_display()})"
            for b in baixas_cancelaveis
        )
        self.message_user(
            request,
            ("Serão canceladas as seguintes Baixas Físicas: " f"{lista_cancelaveis}"),
            level=messages.INFO,
        )

        canceladas = 0
        for baixa in baixas_cancelaveis:

            for item in baixa.itens.select_related("bem"):
                bem = item.bem
                if bem.status == constants.BAIXA_FISICA_AGUARDANDO_APROVACAO:
                    bem.status = constants.APROVADO
                    bem.save(update_fields=["status"])

            baixa.status = constants.CANCELADA
            baixa.save(update_fields=["status"])
            canceladas += 1

            envia_email_baixa_fisica_cancelada(baixa, request.user)

        if canceladas:
            self.message_user(
                request,
                f"{canceladas} Baixa(s) Física(s) cancelada(s) com sucesso.",
                level=messages.SUCCESS,
            )

    acao_cancelar_baixa.short_description = "Cancelar Baixa Física selecionadas"
