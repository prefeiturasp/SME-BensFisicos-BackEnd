from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from inventario.utils_inventario.inventario_utils import criar_itens_inventario

from .models import ParametroInventarioAnual, InventarioUA, ItemInventario
from .forms import InventarioUAAdminForm


from inventario.utils import excluir_ocorrencia
from . import constants


@admin.register(ParametroInventarioAnual)
class ParametroInventarioAnualAdmin(admin.ModelAdmin):
    list_display = (
        "ano_referencia",
        "periodo_final",
        "ativo",
    )
    list_filter = ("ativo", "ano_referencia")
    search_fields = ("ano_referencia",)
    ordering = ("-ano_referencia", "-ativo")


class ItemInventarioInline(admin.TabularInline):
    model = ItemInventario
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
        return getattr(obj.bem, "nome", "-")

    nome_bem.short_description = "Nome do Bem"

    def situacao_display(self, obj):
        if not obj or not obj.pk:
            return "-"

        cores = {
            constants.ENCONTRADO_SEM_DIVERGENCIA: ("#28a745", "white"),
            constants.ENCONTRADO: ("#007bff", "white"),
            constants.NAO_ENCONTRADO: ("#dc3545", "white"),
            constants.DIVERGENTE: ("#ffc107", "#212529"),
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

        if obj.observacao:
            return obj.observacao[:40] + ("..." if len(obj.observacao) > 40 else "")
        if obj.divergencia:
            return f"[Divergência] {obj.divergencia[:30]}" + (
                "..." if len(obj.divergencia) > 30 else ""
            )
        return "-"

    observacao_resumida.short_description = "Observação/Divergência"

    def acoes_inline(self, obj):
        if not obj or not obj.pk:
            return "-"

        if not obj.inventario.esta_aberto:
            return format_html('<span style="color: gray;">Inventário fechado</span>')

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


@admin.register(InventarioUA)
class InventarioUAAdmin(admin.ModelAdmin):
    form = InventarioUAAdminForm

    list_display = [
        "numero_inventario",
        "unidade_administrativa",
        "tipo",
        "status_display",
        "periodo_display",
        "total_itens",
        "criado_em",
    ]
    list_filter = [
        "status",
        "tipo",
    ]
    search_fields = [
        "numero_inventario",
        "unidade_administrativa__nome",
        "unidade_administrativa__codigo",
        "unidade_administrativa__sigla",
    ]

    readonly_fields = [
        "numero_inventario",
        "criado_por",
        "criado_em",
        "fechado_por",
        "fechado_em",
        "total_itens",
    ]

    inlines = [ItemInventarioInline]
    actions = ["action_finalizar_inventario"]

    class Media:
        css = {"all": ("css/hide_crud_icons.css",)}
        js = ("admin/inventario_inventarioua_add.js",)

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
                    "Criar Inventário",
                    {
                        "fields": (
                            "unidade_administrativa",
                            "tipo",
                            "periodo_final",  # só aparece/obrigatório quando EVENTUAL
                        )
                    },
                ),
            )

        return (
            (
                "Dados Básicos",
                {
                    "fields": (
                        "numero_inventario",
                        "unidade_administrativa",
                        "tipo",
                        "periodo_final",
                        "status",
                    )
                },
            ),
            (
                "Auditoria",
                {"fields": ("criado_por", "criado_em", "fechado_por", "fechado_em")},
            ),
        )

    def periodo_display(self, obj):
        # anual não tem período
        if obj.tipo == constants.INVENTARIO_ANUAL:
            return "-"

        if not obj.periodo_final:
            return "-"

        return format_html("<strong>Até {}</strong>", obj.periodo_final.strftime("%d/%m/%Y"))

    periodo_display.short_description = "Período"
    periodo_display.admin_order_field = "periodo_final"
    
    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        ua = getattr(request.user, "unidade_administrativa", None)
        if (
            request.user.is_operador_inventario
            and not request.user.is_gestor_patrimonio
        ):
            return qs.filter(unidade_administrativa=ua) if ua else qs.none()

        return qs

    def save_model(self, request, obj, form, change):
        if not change:
            obj.criado_por = request.user
        super().save_model(request, obj, form, change)

        # Após criar: montar itens automaticamente com as regras
        if not change:
            criar_itens_inventario(obj)
            messages.success(
                request,
                f"Inventário criado com sucesso! {obj.itens.count()} itens foram adicionados automaticamente.",
            )

    def status_display(self, obj):
        cores = {
            constants.INVENTARIO_EM_ABERTO: "#28a745",
            constants.INVENTARIO_FECHADO: "#6c757d",
        }
        cor = cores.get(obj.status, "#000")

        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; '
            'border-radius: 3px; font-weight: bold;">{}</span>',
            cor,
            obj.get_status_display(),
        )

    status_display.short_description = "Status"
    status_display.admin_order_field = "status"

    # def periodo_display(self, obj):
    #     if not obj.periodo_inicial or not obj.periodo_final:
    #         return "-"
    #     return format_html(
    #         "<strong>{}</strong> → <strong>{}</strong>",
    #         obj.periodo_inicial.strftime("%d/%m/%Y"),
    #         obj.periodo_final.strftime("%d/%m/%Y"),
    #     )

    # periodo_display.short_description = "Período"
    # periodo_display.admin_order_field = "periodo_inicial"

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
            "Baixa Física": obj.itens.filter(situacao=constants.BAIXA_FISICA).count(),
        }

        detalhes = " | ".join([f"{k}: {v}" for k, v in por_situacao.items() if v > 0])

        return format_html(
            "<strong>Total: {}</strong><br/><small>{}</small>",
            total,
            detalhes or "—",
        )

    total_itens.short_description = "Itens"

    @admin.action(description="Finalizar inventários selecionados")
    def action_finalizar_inventario(self, request, queryset):
        finalizados = 0
        erros = 0

        for inventario in queryset:
            if inventario.status == constants.INVENTARIO_FECHADO:
                erros += 1
                continue

            try:
                finalizar_inventario(inventario, request.user)
                finalizados += 1
            except Exception as e:
                erros += 1
                messages.error(
                    request,
                    f"Erro ao finalizar {inventario.numero_inventario}: {str(e)}",
                )

        if finalizados > 0:
            messages.success(
                request, f"{finalizados} inventário(s) finalizado(s) com sucesso"
            )

        if erros > 0:
            messages.warning(
                request, f"{erros} inventário(s) não puderam ser finalizados"
            )

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
        ]
        return custom_urls + urls

    def registrar_ocorrencia_view(self, request, item_id):
        try:
            item = ItemInventario.objects.select_related("bem", "inventario").get(
                pk=item_id
            )
        except ItemInventario.DoesNotExist:
            messages.error(request, "Item não encontrado")
            return redirect("admin:inventario_inventarioua_changelist")

        if not item.inventario.esta_aberto:
            messages.error(request, "Inventário fechado não permite edições")
            return redirect("admin:inventario_inventarioua_change", item.inventario.pk)

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
                    "admin:inventario_inventarioua_change", item.inventario.pk
                )
            except ValidationError as e:
                messages.error(request, str(e))

        situacoes_disponiveis = list(constants.SITUACOES_ITEM_INVENTARIO)

        # não permitir registrar "Encontrado sem divergência" manualmente
        situacoes_disponiveis = [
            s
            for s in situacoes_disponiveis
            if s[0] != constants.ENCONTRADO_SEM_DIVERGENCIA
        ]

        # compatível com model atual: não existe situacao_anterior
        # regra original: só permitir "ENCONTRADO" se antes estava "NAO_ENCONTRADO"
        if item.situacao != constants.NAO_ENCONTRADO:
            situacoes_disponiveis = [
                s for s in situacoes_disponiveis if s[0] != constants.ENCONTRADO
            ]

        context = {
            "item": item,
            "situacoes_disponiveis": situacoes_disponiveis,
            "DIVERGENTE": constants.DIVERGENTE,
            "opts": self.model._meta,
            "has_view_permission": self.has_view_permission(request),
            "original": item.inventario,
            "title": f"Registrar Ocorrência - {item.bem.numero_patrimonial}",
        }

        return render(request, "admin/inventario/registrar_ocorrencia.html", context)

    def excluir_ocorrencia_view(self, request, item_id):
        try:
            item = ItemInventario.objects.select_related("bem", "inventario").get(
                pk=item_id
            )
        except ItemInventario.DoesNotExist:
            messages.error(request, "Item não encontrado")
            return redirect("admin:inventario_inventarioua_changelist")

        if not item.inventario.esta_aberto:
            messages.error(request, "Inventário fechado não permite edições")
            return redirect("admin:inventario_inventarioua_change", item.inventario.pk)

        if request.method == "POST":
            try:
                excluir_ocorrencia(item=item, usuario=request.user)
                messages.success(request, "Ocorrência excluída com sucesso")
            except ValidationError as e:
                messages.error(request, str(e))

            return redirect("admin:inventario_inventarioua_change", item.inventario.pk)

        context = {
            "item": item,
            "opts": self.model._meta,
            "title": f"Confirmar exclusão de ocorrência - {item.bem.numero_patrimonial}",
        }

        return render(request, "admin/inventario/excluir_ocorrencia.html", context)
