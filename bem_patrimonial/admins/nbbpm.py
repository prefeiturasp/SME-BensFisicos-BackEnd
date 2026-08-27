from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from rangefilter.filters import DateRangeFilter

from bem_patrimonial.models import NBBPM
from dados_comuns.escopo import resolver_ids_escopo


@admin.register(NBBPM)
class NBBPMAdmin(admin.ModelAdmin):
    list_display = ("numero", "unidade_orcamentaria_display", "unidade_administrativa_display", "responsavel", "data_autorizacao", "total_baixas", "criado_por", "pdf_link_list")
    list_filter = (("data_autorizacao", DateRangeFilter), ("data_criacao", DateRangeFilter))
    search_fields = (
        "numero",
        "numero_processo_baixa",
        "numero_processo_destinacao_final",
        "responsavel",
        "criado_por__username",
        "baixas__numero_processo_baixa",
        "baixas__unidade_administrativa_origem__nome",
        "baixas__unidade_administrativa_origem__sigla",
        "baixas__unidade_administrativa_origem__codigo",
    )
    ordering = ["-data_criacao"]
    actions = None
    change_form_template = "admin/bem_patrimonial/nbbpm/change_form.html"

    # Somente visualização - criação via Baixa Física > Gerar NBBPM
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        user = request.user
        return bool(user.is_authenticated and (user.is_gestor_patrimonio or user.is_superuser or user.is_operador_inventario))

    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("criado_por").prefetch_related("baixas__unidade_administrativa_origem__unidade_orcamentaria", "baixas__itens__bem")
        user = request.user
        is_super, is_gestor, ua_id, uo_id = resolver_ids_escopo(user)
        if ua_id:
            return qs.filter(baixas__unidade_administrativa_origem_id=ua_id).distinct()
        if (is_gestor or is_super) and uo_id:
            return qs.filter(baixas__unidade_administrativa_origem__unidade_orcamentaria_id=uo_id).distinct()
        if is_super and not ua_id and not uo_id:
            return qs
        return qs.none()

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return (
                "numero",
                "numero_processo_baixa",
                "data_autorizacao",
                "responsavel",
                "numero_processo_destinacao_final",
                "criado_por",
                "data_criacao",
                "unidade_orcamentaria_display",
                "unidade_administrativa_display",
                "baixas_detail",
                "bens_detail",
            )
        return ("numero", "data_criacao")

    def get_fieldsets(self, request, obj=None):
        if obj:
            return (
                ("Dados da NBBPM", {"fields": ("numero", "numero_processo_baixa", "data_autorizacao", "responsavel", "numero_processo_destinacao_final", "unidade_orcamentaria_display", "unidade_administrativa_display", "criado_por", "data_criacao")}),
                ("Baixas vinculadas", {"fields": ("baixas_detail",)}),
                ("Bens vinculados", {"fields": ("bens_detail",)}),
            )
        return ((None, {"fields": ("numero", "data_criacao")}),)

    def total_baixas(self, obj):
        return obj.baixas.count()
    total_baixas.short_description = "Quantidade de Baixas"

    def unidade_administrativa_display(self, obj):
        ua = obj.unidade_administrativa_origem
        if ua:
            return f"{ua.sigla or ''} - {ua.nome or ''} ({ua.codigo or ''})".strip()
        return "-"
    unidade_administrativa_display.short_description = "Unidade Administrativa"

    def unidade_orcamentaria_display(self, obj):
        uo = obj.unidade_orcamentaria
        if uo:
            return f"{uo.sigla or ''} - {uo.nome or ''} ({uo.codigo or ''})".strip()
        return "-"
    unidade_orcamentaria_display.short_description = "Unidade Orçamentária"

    def pdf_link_list(self, obj):
        url = reverse("admin:nbbpm_pdf", args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank" style="background:#198754; border-color:#198754; color:#fff !important; padding:4px 10px; text-decoration:none;">PDF</a>',
            url,
        )
    pdf_link_list.short_description = "PDF"

    def baixas_detail(self, obj):
        baixas = obj.baixas.select_related("unidade_administrativa_origem", "unidade_administrativa_origem__unidade_orcamentaria", "criado_por", "aprovado_por").prefetch_related("itens__bem").all()
        if not baixas:
            return "-"
        rows = []
        for baixa in baixas:
            ua = baixa.unidade_administrativa_origem
            ua_label = f"{ua.sigla} - {ua.nome}" if ua else "-"
            uo = getattr(ua, "unidade_orcamentaria", None) if ua else None
            uo_label = f"{uo.sigla} - {uo.nome}" if uo else "-"
            total_itens = baixa.itens.count()
            link = reverse("admin:bem_patrimonial_baixafisicabempatrimonial_change", args=[baixa.pk])
            rows.append(
                f'<tr><td><a href="{link}">#{baixa.pk}</a></td>'
                f"<td>{baixa.numero_processo_baixa or '-'}</td>"
                f"<td>{uo_label}</td>"
                f"<td>{ua_label}</td>"
                f"<td>{baixa.get_status_display()}</td>"
                f"<td>{total_itens}</td>"
                f"<td>{baixa.criado_por or '-'}</td>"
                f"<td>{baixa.data_aprovacao.strftime('%d/%m/%Y %H:%M') if baixa.data_aprovacao else '-'}</td></tr>"
            )
        html = (
            '<table class="adminlist" style="width:100%; border-collapse:collapse;">'
            "<thead><tr>"
            "<th style='padding:4px; border:1px solid #ddd;'>Baixa</th>"
            "<th style='padding:4px; border:1px solid #ddd;'>Processo</th>"
            "<th style='padding:4px; border:1px solid #ddd;'>Unidade Orçamentária</th>"
            "<th style='padding:4px; border:1px solid #ddd;'>Unidade Administrativa</th>"
            "<th style='padding:4px; border:1px solid #ddd;'>Status</th>"
            "<th style='padding:4px; border:1px solid #ddd;'>Itens</th>"
            "<th style='padding:4px; border:1px solid #ddd;'>Solicitante</th>"
            "<th style='padding:4px; border:1px solid #ddd;'>Aprovação</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
        return format_html(html)
    baixas_detail.short_description = ""

    def bens_detail(self, obj):
        from bem_patrimonial.nbbpm_lote import obter_bens_nbbpm_lote

        bens = obter_bens_nbbpm_lote(obj)
        if not bens:
            return format_html("<em>Nenhum bem vinculado.</em>")
        rows = []
        total_valor = 0
        for bem in bens:
            valor = getattr(bem, "valor_unitario", 0) or 0
            try:
                total_valor += float(valor)
            except Exception:
                pass
            rows.append(
                f"<tr><td>{bem.numero_patrimonial or '-'}</td>"
                f"<td>{bem.nome or bem.descricao or '-'}</td>"
                f"<td>{valor}</td>"
                f"<td>{bem.marca or '-'}</td>"
                f"<td>{bem.modelo or '-'}</td></tr>"
            )
        html = (
            '<table class="adminlist" style="width:100%; border-collapse:collapse;">'
            "<thead><tr>"
            "<th style='padding:4px; border:1px solid #ddd;'>Número Patrimonial</th>"
            "<th style='padding:4px; border:1px solid #ddd;'>Descrição</th>"
            "<th style='padding:4px; border:1px solid #ddd;'>Valor unitário</th>"
            "<th style='padding:4px; border:1px solid #ddd;'>Marca</th>"
            "<th style='padding:4px; border:1px solid #ddd;'>Modelo</th>"
            "</tr></thead><tbody>"
            + "".join(rows)
            + f"<tr style='font-weight:bold; background:#f5f5f5;'><td colspan='2'>TOTAL GERAL</td><td>{total_valor:.2f}</td><td colspan='2'>{len(bens)} bem(ns)</td></tr>"
            + "</tbody></table>"
        )
        return format_html(html)
    bens_detail.short_description = ""

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:object_id>/pdf/",
                self.admin_site.admin_view(self.pdf_view),
                name="nbbpm_pdf",
            ),
        ]
        return custom + urls

    def pdf_view(self, request, object_id):
        obj = self.get_object(request, object_id)
        if obj is None:
            from django.http import Http404

            raise Http404("NBBPM não encontrada")
        # Checa permissão de visualização
        if not self.has_view_permission(request, obj):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        # Garante que objeto está no escopo
        qs = self.get_queryset(request).filter(pk=obj.pk)
        if not qs.exists():
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Fora do seu escopo de acesso")
        from bem_patrimonial.nbbpm_lote import http_response_nbbpm_lote

        return http_response_nbbpm_lote(obj, usuario_gerador=request.user)
