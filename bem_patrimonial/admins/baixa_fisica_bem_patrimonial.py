from django import forms
from django.urls import path, reverse
from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError
from django.forms import DateInput
from django.db import models
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.http import HttpResponseRedirect
from django.utils.formats import date_format
from django.utils.html import format_html
from rangefilter.filters import DateRangeFilter
from import_export import resources, fields
from import_export.widgets import DateWidget
from import_export.admin import ExportMixin
from import_export.formats.base_formats import XLSX

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
from dados_comuns.escopo import (
    filtrar_queryset_por_escopo,
    filtrar_ua_origem_por_escopo,
    usuario_e_super_admin,
)
from dados_comuns.models import UnidadeAdministrativa


class NBBPMGerarAdminForm(forms.Form):
    numero_processo_baixa = forms.CharField(
        label="Número do processo de Baixa",
        max_length=64,
        required=True,
        widget=forms.TextInput(attrs={"class": "vTextField"}),
    )
    data_autorizacao = forms.DateField(
        label="Data da Autorização",
        required=True,
        widget=DateInput(attrs={"type": "date"}),
        initial=timezone.localdate,
    )
    responsavel = forms.CharField(
        label="Responsável",
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={"class": "vTextField"}),
    )
    numero_processo_destinacao_final = forms.CharField(
        label="Número do processo de destinação final",
        max_length=64,
        required=False,
        widget=forms.TextInput(attrs={"class": "vTextField"}),
    )


class SolicitarCorrecaoAdminForm(forms.Form):
    motivo = forms.CharField(
        label="Orientações para correção",
        required=True,
        widget=forms.Textarea(attrs={"rows": 4, "class": "vLargeTextField", "placeholder": "Descreva o que precisa ser corrigido..."}),
        help_text="O motivo será registrado no histórico e a baixa voltará para 'Em elaboração' para edição.",
    )


class BaixaFisicaBensItemInlineForm(forms.ModelForm):
    class Meta:
        model = BaixaFisicaBensItem
        fields = ("bem",)

    def clean_bem(self):
        bem = self.cleaned_data.get("bem")
        if not bem:
            return bem
        from bem_patrimonial.models import BaixaFisicaBensItem as ItemModel
        from bem_patrimonial import constants as bem_constants

        # Status bloqueados — igual API _STATUS_BEM_INVALIDOS_PARA_BAIXA
        bloqueados = {
            bem_constants.BAIXA_FISICA_AGUARDANDO_APROVACAO,
            bem_constants.BLOQUEADO,
            bem_constants.BAIXA_FISICA,
            bem_constants.TRANSFERIDO,
        }
        if bem.status in bloqueados:
            baixa_atual = getattr(self.instance, "baixa_id", None) or getattr(getattr(self, "_baixa_fk", None), "pk", None)
            try:
                parent_baixa = getattr(self, "parent_baixa", None)
                if parent_baixa:
                    baixa_atual = parent_baixa.pk
            except Exception:
                pass
            if bem.status == bem_constants.BAIXA_FISICA_AGUARDANDO_APROVACAO:
                existe_outra = ItemModel.objects.filter(
                    bem=bem,
                    baixa__status__in=[
                        bem_constants.AGUARDANDO_ENVIO,
                        bem_constants.SOLICITADA,
                        bem_constants.ACEITA,
                    ],
                ).exclude(baixa_id=baixa_atual).exists()
                if existe_outra:
                    raise ValidationError(
                        f"Bem {bem.numero_patrimonial or bem.nome} já está em outra Baixa Física pendente/aprovada."
                    )
            else:
                raise ValidationError(
                    f"Bem {bem.numero_patrimonial or bem.nome} com status '{bem.get_status_display()}' não pode ser incluído em Baixa Física."
                )
        baixa = getattr(self.instance, "baixa", None)
        if baixa and getattr(baixa, "unidade_administrativa_origem_id", None):
            if bem.unidade_administrativa_id != baixa.unidade_administrativa_origem_id:
                raise ValidationError(
                    f"Bem {bem.numero_patrimonial} não pertence à UA da Baixa ({baixa.unidade_administrativa_origem})."
                )
        return bem


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
    form = BaixaFisicaBensItemInlineForm
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
            # Filtra bens disponíveis: só APROVADO (e os já nesta baixa quando em elaboração)
            try:
                from bem_patrimonial.models import BemPatrimonial

                if obj and obj.status == constants.AGUARDANDO_ENVIO and obj.pk:
                    ids_atuais = list(obj.itens.values_list("bem_id", flat=True))
                    qs = BemPatrimonial.objects.filter(
                        models.Q(status=constants.APROVADO) | models.Q(pk__in=ids_atuais)
                    )
                    if obj.unidade_administrativa_origem_id:
                        qs = qs.filter(unidade_administrativa_id=obj.unidade_administrativa_origem_id)
                    bem_field.queryset = qs
                elif obj is None:
                    base_qs = BemPatrimonial.objects.filter(status=constants.APROVADO)
                    ua_user = getattr(request.user, "unidade_administrativa", None)
                    if ua_user and not usuario_e_super_admin(request.user):
                        bem_field.queryset = base_qs.filter(unidade_administrativa_id=ua_user.pk)
                    else:
                        bem_field.queryset = base_qs
            except Exception:
                pass

        return formset

    def has_add_permission(self, request, obj):

        if obj is None:
            return True

        return obj.status == constants.AGUARDANDO_ENVIO

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return True
        return obj.status == constants.AGUARDANDO_ENVIO

    def get_max_num(self, request, obj=None):

        if obj is not None and obj.status != constants.AGUARDANDO_ENVIO:
            return 0
        return super().get_max_num(request, obj)

    def get_readonly_fields(self, request, obj=None):

        if obj and obj.status != constants.AGUARDANDO_ENVIO:
            return ("bem",)
        return super().get_readonly_fields(request, obj)


class BaixaFisicaResource(resources.ModelResource):
    unidade_administrativa = fields.Field(
        attribute="unidade_administrativa_origem__nome",
        column_name="Unidade Administrativa",
    )

    numero_patrimonial = fields.Field(
        column_name="Número Patrimonial"
    )

    nome_bem = fields.Field(
        column_name="Nome do Bem"
    )

    status = fields.Field(
        attribute="status",
        column_name="Status",
    )

    nbbpm = fields.Field(
        column_name="NBBPM",
    )

    criado_por = fields.Field(
        attribute="criado_por__username",
        column_name="Usuário que solicitou",
    )

    aprovado_por = fields.Field(
        attribute="aprovado_por__username",
        column_name="Gestor que aprovou",
    )

    data_aprovacao = fields.Field(
        attribute="data_aprovacao",
        column_name="Data da Aprovação",
        widget=DateWidget(format="%d/%m/%Y"),
    )

    class Meta:
        model = BaixaFisicaBemPatrimonial
        fields = (
            "unidade_administrativa",
            "numero_patrimonial",
            "nome_bem",
            "status",
            "nbbpm",
            "criado_por",
            "aprovado_por",
            "data_aprovacao",
        )
        export_order = fields

    def dehydrate_numero_patrimonial(self, obj):
        itens = obj.itens.all()
        return ", ".join(
            item.bem.numero_patrimonial for item in itens if item.bem
        )

    def dehydrate_nome_bem(self, obj):
        itens = obj.itens.all()
        return ", ".join(
            item.bem.nome for item in itens if item.bem
        )

    def dehydrate_nbbpm(self, obj):
        try:
            if hasattr(obj, '_prefetched_objects_cache') and 'nbbpms_lote' in obj._prefetched_objects_cache:
                lotes = obj._prefetched_objects_cache['nbbpms_lote']
                nbbpm = lotes[0] if lotes else None
            else:
                nbbpm = obj.nbbpms_lote.first()
            if nbbpm and nbbpm.numero:
                return nbbpm.numero
        except Exception:
            pass
        return obj.numero_nbbpm or "-"


class BaixaFisicaBemPatrimonialAdmin(ExportMixin, admin.ModelAdmin):
    resource_class = BaixaFisicaResource

    def numero_nbbpm_display(self, obj):
        try:
            nbbpm = obj.nbbpms_lote.first()
            if nbbpm and nbbpm.numero:
                url = reverse("admin:bem_patrimonial_nbbpm_change", args=[nbbpm.pk])
                return format_html('<a href="{}">{}</a>', url, nbbpm.numero)
        except Exception:
            pass
        legado = (obj.numero_nbbpm or "").strip()
        if legado:
            return legado
        return "-"
    numero_nbbpm_display.short_description = "NBBPM"
    numero_nbbpm_display.admin_order_field = "numero_nbbpm"

    def status_display(self, obj):
        if obj.status == constants.AGUARDANDO_ENVIO:
            return "Em elaboração"
        return obj.get_status_display()
    status_display.short_description = "Status"
    status_display.admin_order_field = "status"

    def laudo_link(self, obj):
        if obj.status != constants.ACEITA:
            return "-"
        url = reverse("admin:baixafisica_laudo", args=[obj.pk])
        return format_html(
            '<a href="{}" target="_blank" style="background:#198754; border-color:#198754; color:#fff !important; padding:3px 8px; border-radius:3px; text-decoration:none; font-size:11px;">Laudo</a>',
            url,
        )
    laudo_link.short_description = "Laudo"

    def nbbpm_link(self, obj):
        return self.numero_nbbpm_display(obj)
    nbbpm_link.short_description = "NBBPM (link)"

    list_display = (
        "id",
        "numero_nbbpm_display",
        "unidade_administrativa_origem",
        "status_display",
        "criado_por",
        "aprovado_por",
        "data_aprovacao_formatada",
        "laudo_link",
    )
    ordering = ["-data_criacao"]
    list_filter = (
        "status",
        ("data_criacao", DateRangeFilter),
        ("data_aprovacao", DateRangeFilter),
    )
    list_display_links = ("id",)
    search_fields = (
        "numero_processo_baixa",
        "numero_nbbpm",
        "nbbpms_lote__numero",
        "unidade_administrativa_origem__nome",
        "unidade_administrativa_origem__sigla",
        "unidade_administrativa_origem__codigo",
        "criado_por__username",
        "aprovado_por__username",
        "itens__bem__numero_patrimonial",
        "itens__bem__nome",
    )

    def get_export_formats(self):
        return [XLSX]

    def get_export_queryset(self, request):
        qs = super().get_export_queryset(request)
        qs = filtrar_queryset_por_escopo(
            usuario=request.user,
            queryset=qs,
            campo_ua="unidade_administrativa_origem",
        )
        return qs.prefetch_related("itens__bem", "nbbpms_lote").order_by("-id")

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
        js = ("admin/baixa_fisica_autocomplete.js",)
        css = {
            "all": (
                "css/hide_crud_icons.css",
                "css/baixa_fisica_inline.css",
                "css/custom_baixa_fisica.css",
            )
        }

    def get_readonly_fields(self, request, obj=None):
        # Após criação, processo e data_baixa ficam readonly; em elaboração só itens são editáveis via inline
        base_audit = ("status", "criado_por", "data_criacao", "aprovado_por", "data_aprovacao")
        if obj is None:
            # Criação: permite editar UA, processo e data_baixa
            return base_audit
        # Em elaboração ou qualquer status posterior: trava processo/data/UA
        return base_audit + ("unidade_administrativa_origem", "numero_processo_baixa", "data_baixa")

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
        conforme inclusão/remoção/alteração de itens, mas APENAS quando
        a baixa está em status 'aguardando envio' (Em elaboração).
        Igual API: PATCH /baixa-fisica/{id}/ só permite `itens`.
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

            # Alteração de bem em linha existente (troca de patrimônio)
            for form in getattr(formset, "forms", []):
                if form in getattr(formset, "deleted_forms", []):
                    continue
                if "bem" not in getattr(form, "changed_data", []):
                    continue
                # Restaura bem antigo
                old_bem_id = (form.initial or {}).get("bem")
                if old_bem_id:
                    try:
                        from bem_patrimonial.models import BemPatrimonial

                        old_bem = BemPatrimonial.objects.get(pk=old_bem_id)
                        if old_bem.status == constants.BAIXA_FISICA_AGUARDANDO_APROVACAO:
                            # Só restaura se não estiver em outra baixa pendente/aprovada
                            ainda_vinculado = BaixaFisicaBensItem.objects.filter(
                                bem=old_bem,
                                baixa__status__in=[
                                    constants.AGUARDANDO_ENVIO,
                                    constants.SOLICITADA,
                                    constants.ACEITA,
                                ],
                            ).exclude(baixa=baixa).exists()
                            if not ainda_vinculado:
                                old_bem.status = constants.APROVADO
                                old_bem.save(update_fields=["status"])
                    except Exception:
                        pass
                # Garante novo bem em aguardando aprovação
                try:
                    new_bem = form.cleaned_data.get("bem")
                    if new_bem and new_bem.status != constants.BAIXA_FISICA_AGUARDANDO_APROVACAO:
                        new_bem.status = constants.BAIXA_FISICA_AGUARDANDO_APROVACAO
                        new_bem.save(update_fields=["status"])
                except Exception:
                    pass

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
            .select_related("unidade_administrativa_origem", "unidade_administrativa_origem__unidade_orcamentaria", "criado_por")
            .prefetch_related("nbbpms_lote")
        )
        return filtrar_queryset_por_escopo(
            usuario=request.user,
            queryset=qs,
            campo_ua="unidade_administrativa_origem",
        ).distinct()

    def changelist_view(self, request, extra_context=None):
        user = request.user
        ua = getattr(user, "unidade_administrativa", None)

        if user.is_operador_inventario and not ua:
            messages.warning(
                request,
                "Como operador você deve estár vinculado a uma unidade administrativa",
            )

        return super().changelist_view(request, extra_context=extra_context)

    actions = [
        "acao_enviar_baixa",
        "acao_aprovar_baixa",
        "acao_cancelar_baixa",
        "acao_solicitar_correcao",
        "gerar_nbbpm_action",
    ]

    def get_actions(self, request):
        actions = super().get_actions(request)

        actions.pop("delete_selected", None)

        if not (request.user.is_gestor_patrimonio or request.user.is_superuser):
            actions.pop("acao_aprovar_baixa", None)
            actions.pop("acao_cancelar_baixa", None)
            actions.pop("gerar_nbbpm_action", None)
            # acao_solicitar_correcao permanece visível: gestor/super ou criador (validado no action)

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
                    "pois não estão com status 'Em Elaboração': "
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
            self.log_change(
                request,
                baixa,
                "Baixa Física solicitada para aprovação.",
            )
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
            try:
                baixa.aprovar(usuario_aprovador=request.user)
            except ValidationError as e:
                self.message_user(
                    request,
                    f"Baixa #{baixa.pk}: {e.messages[0] if hasattr(e, 'messages') else str(e)}",
                    level=messages.ERROR,
                )
                continue
            except Exception as e:
                self.message_user(
                    request,
                    f"Baixa #{baixa.pk}: erro ao aprovar: {e}",
                    level=messages.ERROR,
                )
                continue
            self.log_change(
                request,
                baixa,
                "Baixa Física aprovada.",
            )
            envia_email_baixa_fisica_aprovada(baixa)
            aprovadas += 1

        if aprovadas:
            self.message_user(
                request,
                f"{aprovadas} Baixa(s) Física(s) aprovada(s) com sucesso. Selecione as aprovadas e use 'Gerar NBBPM' para emitir a nota.",
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
                    "'Em Elaboração' ou 'Solicitada'. Nada foi recusado."
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
            self.log_change(
                request,
                baixa,
                "Baixa Física recusada.",
            )
            canceladas += 1

            envia_email_baixa_fisica_cancelada(baixa, request.user)

        if canceladas:
            self.message_user(
                request,
                f"{canceladas} Baixa(s) Física(s) cancelada(s) com sucesso.",
                level=messages.SUCCESS,
            )

    acao_cancelar_baixa.short_description = "Recusar Baixa Física selecionadas"

    def acao_solicitar_correcao(self, request, queryset):
        user = request.user
        is_gestor = bool(user.is_gestor_patrimonio or user.is_superuser)
        # Operador criador pode devolver sua própria baixa (além do gestor)
        if not is_gestor:
            nao_criadas = [b for b in queryset if b.criado_por_id != user.pk]
            if nao_criadas:
                self.message_user(request, "Apenas Gestor de Patrimônio ou o solicitante da baixa pode solicitar correção.", level=messages.ERROR)
                return

        solicitadas = queryset.filter(status=constants.SOLICITADA)
        nao_solicitadas = queryset.exclude(status=constants.SOLICITADA)
        if nao_solicitadas.exists():
            lista = ", ".join(f"#{b.pk} ({b.get_status_display()})" for b in nao_solicitadas[:10])
            self.message_user(
                request,
                f"Solicitar correção só é permitido para Baixas com status 'Solicitada'. Não elegíveis: {lista}",
                level=messages.ERROR,
            )
            return
        if not solicitadas.exists():
            self.message_user(request, "Nenhuma Baixa selecionada com status 'Solicitada'.", level=messages.WARNING)
            return

        escopo_ids = set(
            filtrar_queryset_por_escopo(
                usuario=request.user,
                queryset=BaixaFisicaBemPatrimonial.objects.all(),
                campo_ua="unidade_administrativa_origem",
            ).values_list("id", flat=True)
        )
        fora_escopo = [b for b in solicitadas if b.id not in escopo_ids]
        if fora_escopo:
            self.message_user(request, "Uma ou mais Baixas selecionadas não pertencem ao seu escopo.", level=messages.ERROR)
            return

        if request.POST.get("apply_correcao"):
            form = SolicitarCorrecaoAdminForm(request.POST)
            if form.is_valid():
                motivo = form.cleaned_data["motivo"]
                from bem_patrimonial.emails import envia_email_baixa_fisica_correcao_solicitada

                count = 0
                for baixa in solicitadas:
                    baixa.status = constants.AGUARDANDO_ENVIO
                    baixa.save(update_fields=["status"])
                    self.log_change(request, baixa, f"Correção solicitada: {motivo}")
                    try:
                        # Historico
                        from dados_comuns.models import HistoricoGeral
                        from django.contrib.contenttypes.models import ContentType

                        ct = ContentType.objects.get_for_model(BaixaFisicaBemPatrimonial)
                        HistoricoGeral.objects.create(
                            content_type=ct,
                            object_id=str(baixa.pk),
                            campo="status",
                            valor_antigo="Solicitada",
                            valor_novo="Em elaboração",
                            alterado_por=request.user,
                            justificativa=f"Correção solicitada. Orientações: {motivo}",
                        )
                    except Exception:
                        pass
                    try:
                        envia_email_baixa_fisica_correcao_solicitada(baixa, request.user)
                    except Exception:
                        pass
                    count += 1
                self.message_user(
                    request,
                    f"{count} Baixa(s) retornada(s) para 'Em elaboração' para correção. Os bens permanecem em 'Aguardando aprovação' para reedição.",
                    level=messages.SUCCESS,
                )
                return HttpResponseRedirect(request.get_full_path())
        else:
            form = SolicitarCorrecaoAdminForm()

        context = dict(
            self.admin_site.each_context(request),
            title="Solicitar correção da Baixa",
            baixas=solicitadas.select_related("unidade_administrativa_origem", "unidade_administrativa_origem__unidade_orcamentaria", "criado_por").prefetch_related("itens__bem"),
            form=form,
            opts=self.model._meta,
            action_checkbox_name=ACTION_CHECKBOX_NAME,
            media=self.media,
        )
        return TemplateResponse(request, "admin/bem_patrimonial/baixa_fisica/solicitar_correcao.html", context)

    acao_solicitar_correcao.short_description = "Solicitar correção (voltar para Em elaboração)"

    def gerar_nbbpm_action(self, request, queryset):
        if not (request.user.is_gestor_patrimonio or request.user.is_superuser):
            self.message_user(request, "Apenas Gestor de Patrimônio pode gerar NBBPM.", level=messages.ERROR)
            return

        if not queryset.exists():
            self.message_user(request, "Selecione ao menos uma Baixa Física.", level=messages.WARNING)
            return

        nao_aprovadas = queryset.exclude(status=constants.ACEITA)
        if nao_aprovadas.exists():
            lista = ", ".join(f"#{b.pk} ({b.get_status_display()})" for b in nao_aprovadas[:10])
            self.message_user(
                request,
                f"A NBBPM só pode ser gerada para Baixas com status Aprovado. Selecionadas não aprovadas: {lista}",
                level=messages.ERROR,
            )
            return

        ja_com_nbbpm = [b for b in queryset.select_related("unidade_administrativa_origem") if b.nbbpms_lote.exists() or (b.numero_nbbpm or "").strip()]
        if ja_com_nbbpm:
            lista = ", ".join(str(b.pk) for b in ja_com_nbbpm[:10])
            self.message_user(
                request,
                f"As Baixas {lista} já possuem NBBPM e não podem ser reutilizadas.",
                level=messages.ERROR,
            )
            return

        uas = set(queryset.values_list("unidade_administrativa_origem_id", flat=True))
        if len(uas) > 1 or None in uas:
            self.message_user(
                request,
                "Todas as Baixas selecionadas devem pertencer à mesma Unidade Administrativa.",
                level=messages.ERROR,
            )
            return

        # Verifica escopo (garante que todas estão no escopo do usuário)
        from dados_comuns.escopo import filtrar_queryset_por_escopo

        escopo_ids = set(
            filtrar_queryset_por_escopo(
                usuario=request.user,
                queryset=BaixaFisicaBemPatrimonial.objects.all(),
                campo_ua="unidade_administrativa_origem",
            ).values_list("id", flat=True)
        )
        fora_escopo = [b for b in queryset if b.id not in escopo_ids]
        if fora_escopo:
            self.message_user(request, "Uma ou mais Baixas selecionadas não pertencem ao seu escopo de acesso.", level=messages.ERROR)
            return

        if request.POST.get("apply"):
            form = NBBPMGerarAdminForm(request.POST)
            if form.is_valid():
                try:
                    from bem_patrimonial.services.nbbpm_numero import criar_nbbpm_com_retry

                    baixas = list(queryset.select_related("unidade_administrativa_origem").prefetch_related("itens__bem"))
                    nbbpm = criar_nbbpm_com_retry(
                        baixas=baixas,
                        criado_por=request.user,
                        numero_processo_baixa=form.cleaned_data["numero_processo_baixa"],
                        data_autorizacao=form.cleaned_data["data_autorizacao"],
                        responsavel=form.cleaned_data["responsavel"],
                        numero_processo_destinacao_final=form.cleaned_data.get("numero_processo_destinacao_final") or "",
                    )
                    self.message_user(
                        request,
                        f"NBBPM {nbbpm.numero} gerada com sucesso com {len(baixas)} baixa(s).",
                        level=messages.SUCCESS,
                    )
                    return HttpResponseRedirect(reverse("admin:bem_patrimonial_nbbpm_change", args=[nbbpm.pk]))
                except ValidationError as e:
                    self.message_user(request, f"Erro de validação: {e.messages[0] if hasattr(e, 'messages') else str(e)}", level=messages.ERROR)
                except Exception as e:
                    self.message_user(request, f"Erro ao gerar NBBPM: {e}", level=messages.ERROR)
        else:
            initial = {
                "data_autorizacao": timezone.localdate(),
                "responsavel": getattr(request.user, "nome", None) or request.user.username,
                "numero_processo_baixa": (queryset.first().numero_processo_baixa or "") if queryset.count() == 1 else "",
            }
            form = NBBPMGerarAdminForm(initial=initial)

        context = dict(
            self.admin_site.each_context(request),
            title="Gerar NBBPM consolidada",
            baixas=queryset.select_related("unidade_administrativa_origem", "unidade_administrativa_origem__unidade_orcamentaria", "criado_por").prefetch_related("itens__bem"),
            form=form,
            opts=self.model._meta,
            action_checkbox_name=ACTION_CHECKBOX_NAME,
            media=self.media,
        )
        return TemplateResponse(request, "admin/bem_patrimonial/baixa_fisica/gerar_nbbpm.html", context)

    gerar_nbbpm_action.short_description = "Gerar NBBPM para Baixas aprovadas selecionadas"

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
            path(
                "<int:baixa_id>/laudo/",
                self.admin_site.admin_view(self.baixar_laudo),
                name="baixafisica_laudo",
            ),
        ]
        return custom_urls + urls

    def baixar_nbbpm(self, request, baixa_id):
        from django.http import HttpResponse

        return HttpResponse(
            "Rota desativada. Use o módulo NBBPM em /admin/bem_patrimonial/nbbpm/ para visualizar e baixar o PDF consolidado (layout lote).",
            status=410,
            content_type="text/plain",
        )

    def baixar_laudo(self, request, baixa_id):
        baixa = get_object_or_404(BaixaFisicaBemPatrimonial, pk=baixa_id)
        if not self.has_view_permission(request, baixa):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        qs = self.get_queryset(request).filter(pk=baixa.pk)
        if not qs.exists():
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Fora do seu escopo de acesso")
        if baixa.status != constants.ACEITA:
            from django.http import HttpResponse

            return HttpResponse(
                "O Laudo de Avaliação só pode ser gerado para baixas aceitas.",
                status=400,
                content_type="text/plain",
            )
        from bem_patrimonial.laudo_avaliacao import http_response_laudo_avaliacao

        return http_response_laudo_avaliacao(baixa)
