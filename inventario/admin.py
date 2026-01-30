from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.contrib.admin import SimpleListFilter
from django.db.models.functions import ExtractYear
from django.utils.timezone import localdate

from inventario.utils_conciliacao.conciliacao_utils import (
    criar_itens_conciliacao,
    finalizar_conciliacao,
)
from inventario.utils_conciliacao.conciliacao_automatica import (
    processar_conciliacao_anual_automatica,
)

from .models import ParametroConciliacaoAnual, ConciliacaoUA, ItemConciliacao
from .forms import ConciliacaoUAAdminForm


from inventario.conciliacao import excluir_ocorrencia, registrar_ocorrencia
from . import constants


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


@admin.register(ParametroConciliacaoAnual)
class ParametroConciliacaoAnualAdmin(admin.ModelAdmin):
    list_display = (
        "ano_referencia",
        "periodo_final",
        "ativo",
    )
    list_filter = ("ativo", "ano_referencia")
    search_fields = ("ano_referencia",)
    ordering = ("-ano_referencia", "-ativo")


class ItemConciliacaoInline(admin.TabularInline):
    model = ItemConciliacao
    extra = 0
    can_delete = False
    fields = (
        "numero_patrimonial_bem",
        "nome_bem",
        "situacao_display",
        "observacao_resumida",
        "acoes_inline",
    )
    readonly_fields = (
        "numero_patrimonial_bem",
        "nome_bem",
        "situacao_display",
        "observacao_resumida",
        "acoes_inline",
    )
    ordering = ["bem__numero_patrimonial"]

    def has_add_permission(self, request, obj=None):
        return False

    def numero_patrimonial_bem(self, obj):
        return getattr(obj.bem, "numero_patrimonial", "-")

    numero_patrimonial_bem.short_description = "Número Patrimonial"

    def nome_bem(self, obj):
        nome = getattr(obj.bem, "nome", None)

        if not nome:
            return "-"

        return format_html(
            '<div style="max-width: 360px; white-space: pre-wrap; word-wrap: break-word;">{}</div>',
            nome,
        )

    def situacao_display(self, obj):
        if not obj or not obj.pk:
            return "-"

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
            '<span style="background-color: {}; color: {}; padding: 3px 8px; '
            'border-radius: 3px; font-size: 11px; font-weight: bold;">{}</span>',
            cor_fundo,
            cor_texto,
            obj.get_situacao_display(),
        )

    situacao_display.short_description = "Situação"

    def observacao_resumida(self, obj):
        if not obj or not obj.pk:
            return "-"

        texto = None

        if obj.observacao:
            texto = obj.observacao
        elif obj.divergencia:
            texto = f"[Divergência] {obj.divergencia}"
        else:
            return "-"

        return format_html(
            '<div style="max-width: 420px; white-space: pre-wrap; word-wrap: break-word;">{}</div>',
            texto,
        )

    observacao_resumida.short_description = "Observação/Divergência"

    def acoes_inline(self, obj):
        if not obj or not obj.pk:
            return "-"

        if not obj.conciliacao.esta_aberto:
            return format_html('<span style="color: gray;">Conciliação fechada</span>')

        if not obj.permite_registrar_ocorrencia:
            return format_html(
                '<button class="button" disabled '
                'style="padding: 3px 10px; font-size: 11px; background-color: #ccc; '
                'border-color: #ccc; color: #666; cursor: not-allowed;" '
                'title="Bem baixado não pode ter status alterado">Registrar</button>'
            )

        botoes = []

        texto_botao = "Editar" if obj.tem_ocorrencia else "Registrar"
        botoes.append(
            f'<a class="button" href="{reverse("admin:inventario_item_registrar_ocorrencia", args=[obj.pk])}" '
            f'style="padding: 3px 10px; font-size: 11px; background-color: #417690; '
            f'border-color: #417690; color: white;">{texto_botao}</a>'
        )

        if obj.tem_ocorrencia:
            botoes.append(
                f'<a class="button" href="{reverse("admin:inventario_item_excluir_ocorrencia", args=[obj.pk])}" '
                f'style="padding: 3px 10px; font-size: 11px; background-color: #ba2121; '
                f'border-color: #ba2121; color: white;">Excluir</a>'
            )

        return mark_safe(" ".join(botoes))

    acoes_inline.short_description = "Ocorrência"


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

    inlines = [ItemConciliacaoInline]
    actions = []

    class Media:
        css = {
            "all": (
                "css/hide_crud_icons.css",
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

        extra_context["show_save"] = (obj is None) or (obj and obj.esta_aberto)

        return super().changeform_view(request, object_id, form_url, extra_context)

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        ua = getattr(request.user, "unidade_administrativa", None)
        if ua:
            return qs.filter(unidade_administrativa=ua)

        if request.user.is_gestor_patrimonio or request.user.is_superuser:
            return qs

        return qs.none()

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
        url = reverse("admin:inventario_conciliacaoua_change", args=[obj.pk])
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

    def finalizar_conciliacao_view(self, request, pk: int):
        obj = self.get_object(request, pk)
        if not obj:
            messages.error(request, "Conciliação não encontrada.")
            return redirect("admin:inventario_conciliacaoua_changelist")

        if not obj.esta_aberto:
            messages.warning(request, "Conciliação já está finalizada.")
            return redirect("admin:inventario_conciliacaoua_change", obj.pk)

        if request.method == "POST":
            try:
                finalizar_conciliacao(obj, request.user)
                messages.success(request, "Conciliação finalizada com sucesso.")
            except Exception as e:
                messages.error(request, f"Erro ao finalizar conciliação: {e}")

        return redirect("admin:inventario_conciliacaoua_change", obj.pk)

    def registrar_ocorrencia_view(self, request, item_id):
        try:
            item = ItemConciliacao.objects.select_related("bem", "conciliacao").get(
                pk=item_id
            )
        except ItemConciliacao.DoesNotExist:
            messages.error(request, "Item não encontrado")
            return redirect("admin:inventario_conciliacaoua_changelist")

        if not item.conciliacao.esta_aberto:
            messages.error(request, "Conciliação fechada não permite edições")
            return redirect(
                "admin:inventario_conciliacaoua_change", item.conciliacao.pk
            )

        if not item.permite_registrar_ocorrencia:
            messages.error(
                request,
                "Bem com status 'Baixa Física' não pode ter ocorrência registrada. "
                "Este status é definitivo.",
            )
            return redirect(
                "admin:inventario_conciliacaoua_change", item.conciliacao.pk
            )

        if request.method == "POST":
            situacao = request.POST.get("situacao")
            observacao = request.POST.get("observacao", "")
            divergencia = request.POST.get("divergencia", "")

            try:
                registrar_ocorrencia(
                    item=item,
                    situacao=situacao,
                    observacao=observacao,
                    divergencia=divergencia,
                    usuario=request.user,
                )
                messages.success(request, "Ocorrência registrada com sucesso")
                return redirect(
                    "admin:inventario_conciliacaoua_change", item.conciliacao.pk
                )
            except ValidationError as e:
                messages.error(request, str(e))

        situacoes_disponiveis = list(constants.SITUACOES_ITEM_CONCILIACAO)

        # não permitir registrar "Encontrado sem divergência" manualmente
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

        is_edicao = item.tem_ocorrencia
        situacao_atual = item.situacao if is_edicao else None
        observacao_atual = item.observacao if is_edicao else ""
        divergencia_atual = item.divergencia if is_edicao else ""

        context = {
            "item": item,
            "situacoes_disponiveis": situacoes_disponiveis,
            "DIVERGENTE": constants.DIVERGENTE,
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
            "original": item.conciliacao,
            "title": f"Registrar Ocorrência - {item.bem.numero_patrimonial}",
            "is_edicao": is_edicao,
            "situacao_atual": situacao_atual,
            "observacao_atual": observacao_atual,
            "divergencia_atual": divergencia_atual,
        }

        return render(request, "admin/conciliacao/registrar_ocorrencia.html", context)

    def excluir_ocorrencia_view(self, request, item_id):
        try:
            item = ItemConciliacao.objects.select_related("bem", "conciliacao").get(
                pk=item_id
            )
        except ItemConciliacao.DoesNotExist:
            messages.error(request, "Item não encontrado")
            return redirect("admin:inventario_conciliacaoua_changelist")

        if not item.conciliacao.esta_aberto:
            messages.error(request, "Conciliação fechada não permite edições")
            return redirect(
                "admin:inventario_conciliacaoua_change", item.conciliacao.pk
            )

        if request.method == "POST":
            try:
                excluir_ocorrencia(item=item, usuario=request.user)
                messages.success(request, "Ocorrência excluída com sucesso")
            except ValidationError as e:
                messages.error(request, str(e))

            return redirect(
                "admin:inventario_conciliacaoua_change", item.conciliacao.pk
            )

        context = {
            "item": item,
            "opts": self.model._meta,
            "title": f"Confirmar exclusão de ocorrência - {item.bem.numero_patrimonial}",
        }

        return render(request, "admin/conciliacao/excluir_ocorrencia.html", context)

    def changelist_view(self, request, extra_context=None):
        processar_conciliacao_anual_automatica(request.user)
        return super().changelist_view(request, extra_context)
