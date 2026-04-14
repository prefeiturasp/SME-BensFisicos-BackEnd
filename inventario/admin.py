from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.contrib.admin import SimpleListFilter
from urllib.parse import urlencode

from django import forms

from dados_comuns.escopo import (
    filtrar_queryset_por_escopo,
    resolver_ids_escopo,
    usuario_e_super_admin,
)
from inventario.utils_conciliacao.conciliacao_utils import (
    criar_itens_conciliacao,
    finalizar_conciliacao,
    remover_itens_baixados_invalidos,
)
from inventario.utils_conciliacao.conciliacao_automatica import (
    processar_conciliacao_anual_automatica,
)

from . import constants
from .models import ParametroConciliacaoAnual, ConciliacaoUA, ItemConciliacao
from .forms import ConciliacaoUAAdminForm


from inventario.conciliacao import excluir_ocorrencia, registrar_ocorrencia

URL_NAME_CONCILIACAOUA_CHANGE = "admin:inventario_conciliacaoua_change"
URL_NAME_CONCILIACAOUA_CHANGELIST = "admin:inventario_conciliacaoua_changelist"
URL_NAME_ITEMCONCILIACAO_CHANGELIST = "admin:inventario_itemconciliacao_changelist"
URL_NAME_ITEMCONCILIACAO_CHANGE = "admin:inventario_itemconciliacao_change"
HIDE_CRUD_ICONS_CSS = "css/hide_crud_icons.css"
URL_WITH_QUERY_TEMPLATE = "{}?{}"


class AnoVigenciaSelectFilter(SimpleListFilter):
    title = "Ano de Vigência"
    parameter_name = "ano_vigencia"
    template = "admin/filters/ano_select.html"

    def lookups(self, request, model_admin):
        anos = ConciliacaoUA.objects.exclude(periodo_final__isnull=True).dates(
            "periodo_final", "year", order="DESC"
        )
        return [(str(a.year), str(a.year)) for a in anos]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(periodo_final__year=self.value())
        return queryset


class ParametroConciliacaoAnualAdminForm(forms.ModelForm):
    class Meta:
        model = ParametroConciliacaoAnual
        fields = (
            "unidade_orcamentaria",
            "ano_referencia",
            "periodo_inicial",
            "periodo_final",
            "ativo",
        )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        user = getattr(self.request, "user", None)

        if "unidade_orcamentaria" in self.fields:
            fld = self.fields["unidade_orcamentaria"]

            uo_user = getattr(user, "unidade_orcamentaria", None) if user else None

            if uo_user:
                fld.initial = uo_user.pk

                if not fld.queryset.filter(pk=uo_user.pk).exists():
                    fld.queryset = (
                        fld.queryset.model.objects.filter(pk=uo_user.pk) | fld.queryset
                    )

                fld.disabled = True

            if not uo_user and user and not usuario_e_super_admin(user):
                raise ValidationError(
                    "Usuário precisa estar vinculado a uma Unidade Orçamentária (UO)."
                )

        if self.instance and self.instance.pk and "unidade_orcamentaria" in self.fields:
            self.fields["unidade_orcamentaria"].disabled = True

    def clean(self):
        cleaned = super().clean()
        user = getattr(self.request, "user", None)

        if user and not usuario_e_super_admin(user):
            uo_user = getattr(user, "unidade_orcamentaria", None)
            if not uo_user:
                raise ValidationError(
                    "Usuário precisa estar vinculado a uma Unidade Orçamentária (UO)."
                )

            cleaned["unidade_orcamentaria"] = uo_user

        if user and not usuario_e_super_admin(user):
            _is_super, _is_gestor, _ua_id, user_uo_id = resolver_ids_escopo(user)

            cleaned_uo_id = (
                cleaned.get("unidade_orcamentaria").id
                if cleaned.get("unidade_orcamentaria")
                else None
            )
            if cleaned_uo_id != user_uo_id:
                raise ValidationError(
                    {
                        "unidade_orcamentaria": "Você não tem permissão para usar esta UO."
                    }
                )

        return cleaned


@admin.register(ParametroConciliacaoAnual)
class ParametroConciliacaoAnualAdmin(admin.ModelAdmin):
    form = ParametroConciliacaoAnualAdminForm

    list_display = (
        "unidade_orcamentaria",
        "ano_referencia",
        "periodo_final",
        "ativo",
    )
    list_filter = ("ativo", "ano_referencia", "unidade_orcamentaria")
    search_fields = (
        "ano_referencia",
        "unidade_orcamentaria__codigo",
        "unidade_orcamentaria__nome",
    )
    ordering = ("-ano_referencia", "-ativo")

    class Media:
        css = {"all": (HIDE_CRUD_ICONS_CSS,)}

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("unidade_orcamentaria")

        ua = getattr(request.user, "unidade_administrativa", None)

        if ua:
            uo_da_ua_id = getattr(ua, "unidade_orcamentaria_id", None)
            if not uo_da_ua_id:
                return qs.none()
            return qs.filter(unidade_orcamentaria_id=uo_da_ua_id)

        if request.user.is_gestor_patrimonio:
            uo_user_id = getattr(request.user, "unidade_orcamentaria_id", None)
            if not uo_user_id:
                return qs.none()
            return qs.filter(unidade_orcamentaria_id=uo_user_id)

        return qs.none()

    def get_form(self, request, obj=None, **kwargs):
        form_class = super().get_form(request, obj, **kwargs)

        class RequestForm(form_class):
            def __init__(self, *args, **kw):
                kw["request"] = request
                super().__init__(*args, **kw)

        return RequestForm

    def get_readonly_fields(self, request, obj=None):

        ro = list(super().get_readonly_fields(request, obj))
        if obj and "unidade_orcamentaria" not in ro:
            ro.append("unidade_orcamentaria")
        return ro


@admin.register(ItemConciliacao)
class ItemConciliacaoAdmin(admin.ModelAdmin):
    change_list_template = "admin/inventario/itemconciliacao/change_list.html"
    change_form_template = "admin/inventario/itemconciliacao/change_form.html"
    object_history_template = "admin/inventario/itemconciliacao/object_history.html"
    list_display = (
        "numero_patrimonial_bem",
        "nome_bem",
        "situacao_display",
        "observacao_resumida",
        "acoes_lista",
    )
    list_filter = ("situacao",)
    search_fields = (
        "bem__nome",
        "bem__numero_patrimonial",
        "conciliacao__numero_conciliacao",
    )
    ordering = ("bem__numero_patrimonial",)
    actions = []

    class Media:
        css = {
            "all": (
                HIDE_CRUD_ICONS_CSS,
                "css/admin_item_conciliacao.css",
            )
        }

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("bem", "conciliacao")
        return filtrar_queryset_por_escopo(
            usuario=request.user,
            queryset=qs,
            campo_ua="conciliacao__unidade_administrativa",
        )

    def get_model_perms(self, request):
        return {}

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        return {}

    def _get_current_list_url(self):
        return getattr(self, "_current_changelist_full_path", None)

    def _build_action_url(self, url, next_url=None):
        if not next_url:
            return url
        return URL_WITH_QUERY_TEMPLATE.format(url, urlencode({"next": next_url}))

    def _get_item_change_voltar_url(self, request, obj):
        preserved_filters = request.GET.get("_changelist_filters")
        if preserved_filters:
            return URL_WITH_QUERY_TEMPLATE.format(
                reverse(URL_NAME_ITEMCONCILIACAO_CHANGELIST),
                preserved_filters,
            )
        return URL_WITH_QUERY_TEMPLATE.format(
            reverse(URL_NAME_ITEMCONCILIACAO_CHANGELIST),
            urlencode({"conciliacao__id__exact": obj.conciliacao.pk}),
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        if obj:
            extra_context["voltar_url"] = self._get_item_change_voltar_url(request, obj)
        extra_context["show_close"] = False
        extra_context["show_save"] = False
        extra_context["show_save_and_continue"] = False
        extra_context["show_save_and_add_another"] = False
        return super().change_view(request, object_id, form_url, extra_context)

    def history_view(self, request, object_id, extra_context=None):
        extra_context = extra_context or {}
        obj = self.get_object(request, object_id)
        if obj:
            extra_context["lista_url"] = self._get_item_change_voltar_url(request, obj)
            extra_context["change_url"] = reverse(
                "admin:inventario_itemconciliacao_change",
                args=[obj.pk],
            )
            extra_context["voltar_url"] = reverse(
                "admin:inventario_itemconciliacao_change",
                args=[obj.pk],
            )
        return super().history_view(request, object_id, extra_context)

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(
            request, queryset, search_term
        )

        termo = (search_term or "").strip()
        if not termo:
            return queryset, use_distinct

        queryset = queryset.filter(
            Q(bem__numero_patrimonial__icontains=termo)
            | Q(bem__nome__icontains=termo)
        )
        return queryset, use_distinct

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        conciliacao_id = request.GET.get("conciliacao__id__exact")

        if conciliacao_id:
            conciliacao = filtrar_queryset_por_escopo(
                usuario=request.user,
                queryset=ConciliacaoUA.objects.select_related("unidade_administrativa"),
                campo_ua="unidade_administrativa",
            ).filter(pk=conciliacao_id).first()
            if conciliacao:
                extra_context["title"] = (
                    f"Itens da Conciliação {conciliacao.numero_conciliacao}"
                )
                extra_context["conciliacao_origem"] = conciliacao
                extra_context["voltar_conciliacao_url"] = reverse(
                    URL_NAME_CONCILIACAOUA_CHANGE,
                    args=[conciliacao.pk],
                )

        self._current_changelist_full_path = request.get_full_path()
        try:
            return super().changelist_view(request, extra_context)
        finally:
            self._current_changelist_full_path = None

    def numero_patrimonial_bem(self, obj):
        return getattr(obj.bem, "numero_patrimonial", "-")

    numero_patrimonial_bem.short_description = "Número Patrimonial"
    numero_patrimonial_bem.admin_order_field = "bem__numero_patrimonial"

    def nome_bem(self, obj):
        return getattr(obj.bem, "nome", "-")

    nome_bem.short_description = "Nome do Bem"
    nome_bem.admin_order_field = "bem__nome"

    def situacao_display(self, obj):
        cores = {
            constants.ENCONTRADO_SEM_DIVERGENCIA: ("#28a745", "white"),
            constants.ENCONTRADO: ("#007bff", "white"),
            constants.NAO_ENCONTRADO: ("#dc3545", "white"),
            constants.DIVERGENTE: ("#ffc107", "#212529"),
            constants.EM_PROCESSO_BAIXA_FISICA: ("#17a2b8", "white"),
            constants.BAIXA_FISICA: ("#6c757d", "white"),
        }
        cor_fundo, cor_texto = cores.get(obj.situacao, ("#000", "white"))

        return format_html(
            '<span style="display:inline-flex; align-items:center; justify-content:center; '
            'white-space:nowrap; min-width: 148px; box-sizing: border-box; '
            'background-color: {}; color: {}; padding: 3px 8px; '
            'border-radius: 4px; font-size: 11px; font-weight: bold; line-height: 1.2;">{}</span>',
            cor_fundo,
            cor_texto,
            obj.get_situacao_display(),
        )

    situacao_display.short_description = "Situação"
    situacao_display.admin_order_field = "situacao"

    def observacao_resumida(self, obj):
        if obj.observacao:
            return obj.observacao
        if obj.divergencia:
            return f"[Divergência] {obj.divergencia}"
        return "-"

    observacao_resumida.short_description = "Observação/Divergência"

    def acoes_lista(self, obj):
        if not obj.conciliacao.esta_aberto:
            return format_html('<span style="color: gray;">Conciliação fechada</span>')

        if not obj.permite_registrar_ocorrencia:
            return format_html(
                '<button class="button" disabled '
                'style="padding: 3px 10px; font-size: 11px; background-color: #ccc; '
                'border-color: #ccc; color: #666; cursor: not-allowed;" '
                'title="Bem baixado não pode ter status alterado">Registrar</button>'
            )

        texto_botao = "Editar" if obj.tem_ocorrencia else "Registrar"
        next_url = self._get_current_list_url()
        registrar_url = self._build_action_url(
            reverse("admin:inventario_item_registrar_ocorrencia", args=[obj.pk]),
            next_url=next_url,
        )
        botoes = [
            (
                registrar_url,
                texto_botao,
                "#417690",
                "#417690",
            )
        ]

        if obj.tem_ocorrencia:
            excluir_url = self._build_action_url(
                reverse("admin:inventario_item_excluir_ocorrencia", args=[obj.pk]),
                next_url=next_url,
            )
            botoes.append(
                (
                    excluir_url,
                    "Excluir",
                    "#ba2121",
                    "#ba2121",
                )
            )

        return mark_safe(
            '<div style="display:flex; flex-direction:column; align-items:flex-start; gap:4px;">'
            + "".join(
                (
                    f'<a class="button" href="{url}" data-preserve-list-context="true" '
                    f'style="padding: 3px 10px; font-size: 11px; background-color: {cor_fundo}; '
                    f'border-color: {cor_borda}; color: white;">{texto}</a>'
                )
                for url, texto, cor_fundo, cor_borda in botoes
            )
            + "</div>"
        )

    acoes_lista.short_description = "Ocorrência"


@admin.register(ConciliacaoUA)
class ConciliacaoUAAdmin(admin.ModelAdmin):
    form = ConciliacaoUAAdminForm
    change_form_template = "admin/inventario/conciliacaoua/change_form.html"

    list_display = [
        "numero_conciliacao",
        "unidade_administrativa",
        "total_itens",
        "periodo_display",
        "tipo",
        "status_display",
        "acao_visualizar",
    ]
    list_filter = [
        AnoVigenciaSelectFilter,
        "tipo",
        "status",
    ]
    search_fields = [
        "numero_conciliacao",
        "unidade_administrativa__nome",
        "unidade_administrativa__codigo",
        "unidade_administrativa__sigla",
    ]

    readonly_fields = [
        "numero_conciliacao",
        "criado_por",
        "criado_em",
        "fechado_por",
        "fechado_em",
        "total_itens",
        "status_display",
    ]

    inlines = []
    actions = []

    class Media:
        css = {
            "all": (
                HIDE_CRUD_ICONS_CSS,
                "css/admin_filtros.css",
            )
        }
        js = ("admin/conciliacao_conciliacaoua_add.js",)

    def get_model_perms(self, request):
        perms = super().get_model_perms(request)
        self.model._meta.verbose_name_plural = "Gerenciamento de Conciliações"
        return perms

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        return {}

    def get_form(self, request, obj=None, **kwargs):
        """
        Injeta request dentro do form (pra aplicar regras gestor/operador e validações).
        """
        form_class = super().get_form(request, obj, **kwargs)

        class RequestForm(form_class):
            def __new__(cls, *args, **kw):
                kw["request"] = request
                return form_class(*args, **kw)

        return RequestForm

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return (
                (
                    "Criar Conciliação",
                    {
                        "fields": (
                            "unidade_administrativa",
                            "tipo",
                            "periodo_final",
                        )
                    },
                ),
            )

        return (
            (
                "Dados Básicos",
                {
                    "fields": (
                        "numero_conciliacao",
                        "unidade_administrativa",
                        "tipo",
                        "periodo_final",
                        "status_display",
                    )
                },
            ),
            (
                "Auditoria",
                {"fields": ("criado_por", "criado_em", "fechado_por", "fechado_em")},
            ),
        )

    def get_readonly_fields(self, request, obj=None):
        ro = list(super().get_readonly_fields(request, obj))
        if obj and not obj.esta_aberto:
            for f in ("unidade_administrativa", "tipo", "periodo_final"):
                if f not in ro:
                    ro.append(f)
        return ro

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        """
        Remove:
          - Salvar e adicionar outro
          - Salvar e continuar editando
          - Apagar (já removido por has_delete_permission)
        E: Salvar só aparece se conciliação estiver EM_ABERTO
        """
        extra_context = extra_context or {}
        extra_context["show_save_and_add_another"] = False
        extra_context["show_save_and_continue"] = False

        obj = None
        if object_id:
            obj = self.get_object(request, object_id)

        if obj and obj.esta_aberto and request.method == "GET":
            removidos = remover_itens_baixados_invalidos(obj)
            if removidos > 0:
                messages.warning(
                    request,
                    f"{removidos} item(ns) removido(s) automaticamente pois "
                    f"os bens foram baixados a mais de um período.",
                )

        extra_context["show_save"] = (obj is None) or (obj and obj.esta_aberto)
        if obj:
            extra_context["itens_conciliacao_url"] = self._get_itens_conciliacao_url(
                obj
            )

        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("unidade_administrativa")
        return filtrar_queryset_por_escopo(
            usuario=request.user,
            queryset=qs,
            campo_ua="unidade_administrativa",
        )

    def save_model(self, request, obj, form, change):
        if change and "status" in getattr(form, "changed_data", []):
            messages.error(
                request,
                "Status da conciliação só pode ser alterada pela ação 'Fechar conciliação'.",
            )
            return

        if change and obj and not obj.esta_aberto:
            messages.error(request, "Conciliação fechada não permite edições.")
            return

        if not change:
            obj.criado_por = request.user

        super().save_model(request, obj, form, change)

        if not change:
            criar_itens_conciliacao(obj)
            messages.success(
                request,
                f"Conciliação criada com sucesso! {obj.itens.count()} itens foram adicionados automaticamente.",
            )

    def status_display(self, obj):
        cores = {
            constants.CONCILIACAO_EM_ABERTO: "#28a745",
            constants.CONCILIACAO_FECHADO: "#6c757d",
        }
        cor = cores.get(obj.status, "#000")

        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 4px; '
            'border-radius: 3px;">{}</span>',
            cor,
            obj.get_status_display(),
        )

    status_display.short_description = "Status"
    status_display.admin_order_field = "status"

    def periodo_display(self, obj):
        if not obj.periodo_final:
            return "-"
        return format_html(
            "<strong>Até {}</strong>", obj.periodo_final.strftime("%d/%m/%Y")
        )

    periodo_display.short_description = "Período"
    periodo_display.admin_order_field = "periodo_final"

    def total_itens(self, obj):
        if not obj.pk:
            return "-"

        total = obj.itens.count()
        por_situacao = {
            "Encontrados": obj.itens.filter(
                situacao=constants.ENCONTRADO_SEM_DIVERGENCIA
            ).count(),
            "Não encontrados": obj.itens.filter(
                situacao=constants.NAO_ENCONTRADO
            ).count(),
            "Divergentes": obj.itens.filter(situacao=constants.DIVERGENTE).count(),
            "Em processo de baixa": obj.itens.filter(
                situacao=constants.EM_PROCESSO_BAIXA_FISICA
            ).count(),
            "Baixa Física": obj.itens.filter(situacao=constants.BAIXA_FISICA).count(),
        }

        detalhes = " | ".join([f"{k}: {v}" for k, v in por_situacao.items() if v > 0])

        return format_html(
            "<strong>Total: {}</strong><br/><small>{}</small>",
            total,
            detalhes or "—",
        )

    total_itens.short_description = "Itens"

    def acao_visualizar(self, obj):
        url = reverse(URL_NAME_CONCILIACAOUA_CHANGE, args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" '
            'style="padding: 4px 12px; font-size: 12px; color: white;">Visualizar</a>',
            url,
        )

    acao_visualizar.short_description = "Ação"
    acao_visualizar.allow_tags = True

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "item/<int:item_id>/registrar-ocorrencia/",
                self.admin_site.admin_view(self.registrar_ocorrencia_view),
                name="inventario_item_registrar_ocorrencia",
            ),
            path(
                "item/<int:item_id>/excluir-ocorrencia/",
                self.admin_site.admin_view(self.excluir_ocorrencia_view),
                name="inventario_item_excluir_ocorrencia",
            ),
            path(
                "<int:pk>/finalizar/",
                self.admin_site.admin_view(self.finalizar_conciliacao_view),
                name="inventario_conciliacaoua_finalizar",
            ),
        ]
        return custom_urls + urls

    def _get_itens_conciliacao_url(self, conciliacao):
        return URL_WITH_QUERY_TEMPLATE.format(
            reverse(URL_NAME_ITEMCONCILIACAO_CHANGELIST),
            urlencode({"conciliacao__id__exact": conciliacao.pk}),
        )

    def _get_item_conciliacao(self, request, item_id):
        queryset = filtrar_queryset_por_escopo(
            usuario=request.user,
            queryset=ItemConciliacao.objects.select_related("bem", "conciliacao"),
            campo_ua="conciliacao__unidade_administrativa",
        )
        return queryset.filter(pk=item_id).first()

    def _get_voltar_url(self, request, conciliacao):
        return request.GET.get("next") or self._get_itens_conciliacao_url(conciliacao)

    def _validar_item_para_ocorrencia(self, request, item):
        if not item.conciliacao.esta_aberto:
            messages.error(request, "Conciliação fechada não permite edições")
            return redirect(URL_NAME_CONCILIACAOUA_CHANGE, item.conciliacao.pk)

        if item.permite_registrar_ocorrencia:
            return None

        messages.error(
            request,
            "Bem com status 'Baixa Física' não pode ter ocorrência registrada. "
            "Este status é definitivo.",
        )
        return redirect(URL_NAME_CONCILIACAOUA_CHANGE, item.conciliacao.pk)

    def _registrar_ocorrencia_post(self, request, item, voltar_url):
        situacao = request.POST.get("situacao")
        if not situacao:
            return "Selecione uma situação."

        try:
            registrar_ocorrencia(
                item=item,
                situacao=situacao,
                observacao=request.POST.get("observacao", ""),
                divergencia=request.POST.get("divergencia", ""),
                usuario=request.user,
            )
            messages.success(request, "Ocorrência registrada com sucesso")
            return redirect(voltar_url)
        except ValidationError as e:
            return str(e)

    def _get_situacoes_disponiveis_para_item(self, item):
        situacoes_disponiveis = list(constants.SITUACOES_ITEM_CONCILIACAO)
        situacoes_disponiveis = [
            s for s in situacoes_disponiveis if s[0] != constants.BAIXA_FISICA
        ]

        if not item.pode_resolver_situacao:
            situacoes_disponiveis = [
                s
                for s in situacoes_disponiveis
                if s[0] != constants.ENCONTRADO_SEM_DIVERGENCIA
            ]

        if not item.pode_marcar_como_encontrado:
            situacoes_disponiveis = [
                s for s in situacoes_disponiveis if s[0] != constants.ENCONTRADO
            ]

        return situacoes_disponiveis

    def _get_registrar_ocorrencia_context(
        self, request, item, voltar_url, erro_formulario
    ):
        is_edicao = item.tem_ocorrencia
        return {
            **self.admin_site.each_context(request),
            "item": item,
            "situacoes_disponiveis": self._get_situacoes_disponiveis_para_item(item),
            "DIVERGENTE": constants.DIVERGENTE,
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
            "original": item.conciliacao,
            "title": f"Registrar Ocorrência - {item.bem.numero_patrimonial}",
            "is_edicao": is_edicao,
            "situacao_atual": item.situacao if is_edicao else None,
            "observacao_atual": item.observacao if is_edicao else "",
            "divergencia_atual": item.divergencia if is_edicao else "",
            "voltar_url": voltar_url,
            "erro_formulario": erro_formulario,
        }

    def finalizar_conciliacao_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            messages.error(request, "Conciliação não encontrada.")
            return redirect(URL_NAME_CONCILIACAOUA_CHANGELIST)

        if not obj.esta_aberto:
            messages.warning(request, "Conciliação já está finalizada.")
            return redirect(URL_NAME_CONCILIACAOUA_CHANGE, obj.pk)

        if request.method == "POST":
            try:
                finalizar_conciliacao(obj, request.user)
                messages.success(request, "Conciliação finalizada com sucesso.")
            except Exception as e:
                messages.error(request, f"Erro ao finalizar conciliação: {e}")

        return redirect(URL_NAME_CONCILIACAOUA_CHANGE, obj.pk)

    def registrar_ocorrencia_view(self, request, item_id):
        item = self._get_item_conciliacao(request, item_id)
        if not item:
            messages.error(request, "Item não encontrado")
            return redirect(URL_NAME_CONCILIACAOUA_CHANGELIST)

        redirect_response = self._validar_item_para_ocorrencia(request, item)
        if redirect_response:
            return redirect_response

        voltar_url = self._get_voltar_url(request, item.conciliacao)
        erro_formulario = None

        if request.method == "POST":
            resultado_post = self._registrar_ocorrencia_post(request, item, voltar_url)
            if hasattr(resultado_post, "status_code"):
                return resultado_post
            erro_formulario = resultado_post

            if erro_formulario:
                messages.error(request, erro_formulario)

        context = self._get_registrar_ocorrencia_context(
            request=request,
            item=item,
            voltar_url=voltar_url,
            erro_formulario=erro_formulario,
        )

        return render(request, "admin/conciliacao/registrar_ocorrencia.html", context)

    def excluir_ocorrencia_view(self, request, item_id):
        item = self._get_item_conciliacao(request, item_id)
        if not item:
            messages.error(request, "Item não encontrado")
            return redirect(URL_NAME_CONCILIACAOUA_CHANGELIST)

        if not item.conciliacao.esta_aberto:
            messages.error(request, "Conciliação fechada não permite edições")
            return redirect(URL_NAME_CONCILIACAOUA_CHANGE, item.conciliacao.pk)

        voltar_url = request.GET.get("next") or self._get_itens_conciliacao_url(
            item.conciliacao
        )

        if request.method == "POST":
            try:
                excluir_ocorrencia(item=item, usuario=request.user)
                messages.success(request, "Ocorrência excluída com sucesso")
            except ValidationError as e:
                messages.error(request, str(e))

            return redirect(voltar_url)

        context = {
            **self.admin_site.each_context(request),
            "item": item,
            "opts": self.model._meta,
            "title": f"Confirmar exclusão de ocorrência - {item.bem.numero_patrimonial}",
            "voltar_url": voltar_url,
        }

        return render(request, "admin/conciliacao/excluir_ocorrencia.html", context)

    def changelist_view(self, request, extra_context=None):
        processar_conciliacao_anual_automatica(request.user)
        return super().changelist_view(request, extra_context)
