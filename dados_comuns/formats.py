import os
from io import BytesIO
from django.conf import settings
from django.utils import timezone
from django.utils.timezone import localtime
from import_export.formats.base_formats import Format
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
)

from bem_patrimonial.pdf_utils import obter_rf_usuario


class BaseUnidadePDFFormat(Format):

    LOGO_WIDTH_CM = 3
    LOGO_HEIGHT_CM = 1.5
    TABLE_FONT_SIZE = 7

    def get_title(self):
        return "pdf"

    def create_dataset(self, in_stream):
        raise NotImplementedError("Importação não é suportada para PDF.")

    REPORT_TITLE = ""
    EMPTY_MESSAGE = ""
    TABLE_COL_WIDTHS = []

    def get_report_title(self):
        return self.REPORT_TITLE

    def get_empty_message(self):
        return self.EMPTY_MESSAGE

    def get_table_col_widths(self):
        return self.TABLE_COL_WIDTHS

    def get_status_text(self, unidade):
        raise NotImplementedError("Subclasses devem implementar get_status_text().")

    def export_data(self, dataset, **kwargs):
        request = getattr(self, "_export_request", None)
        queryset = getattr(self, "_export_queryset", None)
        unidades = list(queryset) if queryset is not None else []

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=0.3 * cm,
            rightMargin=0.3 * cm,
            topMargin=0.9 * cm,
            bottomMargin=0.9 * cm,
            title=self.get_report_title(),
            author=(
                obter_rf_usuario(request.user)
                if request
                else "Sistema Bens Físicos"
            ),
        )

        elements = self._criar_cabecalho() + self._criar_tabela_unidades(unidades)

        doc.build(
            elements,
            onFirstPage=self._adicionar_numero_pagina,
            onLaterPages=self._adicionar_numero_pagina,
        )

        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    def _carregar_logo(self, filename, fallback_text, styles):
        static_root = settings.STATIC_ROOT or (
            settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else None
        )
        if static_root:
            logo_path = os.path.join(static_root, "img", filename)
            if os.path.exists(logo_path):
                try:
                    return Image(
                        logo_path,
                        width=self.LOGO_WIDTH_CM * cm,
                        height=self.LOGO_HEIGHT_CM * cm,
                    )
                except Exception:
                    pass
        return Paragraph(fallback_text, styles["Heading1"])

    def _resolver_usuario_exportacao(self, request):
        if not request or not hasattr(request, "user") or not request.user.is_authenticated:
            return "Sistema"

        return obter_rf_usuario(request.user)

    def _criar_estilos_celula(self, styles):
        base_kwargs = {
            "parent": styles["Normal"],
            "fontSize": self.TABLE_FONT_SIZE,
            "leading": 8,
            "wordWrap": "CJK",
        }

        cell_style = ParagraphStyle("CellStyle", **base_kwargs)
        cell_style_center = ParagraphStyle(
            "CellStyleCenter",
            alignment=TA_CENTER,
            **base_kwargs,
        )
        return cell_style, cell_style_center

    def _criar_cabecalho(self):
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "CustomTitle",
            parent=styles["Heading1"],
            fontSize=18,
            textColor=colors.HexColor("#149f67"),
            alignment=TA_CENTER,
            spaceAfter=6,
        )
        subtitle_style = ParagraphStyle(
            "CustomSubtitle",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#666666"),
            alignment=TA_CENTER,
        )

        header_row = [
            self._carregar_logo("bens_default_logo.png", "SME", styles),
            [
                Paragraph(self.get_report_title(), title_style),
                Paragraph(
                    "Secretaria Municipal de Educação - Prefeitura de São Paulo",
                    subtitle_style,
                ),
            ],
            self._carregar_logo("prefeitura_default_logo.png", "PMSP", styles),
        ]

        header_table = Table([header_row], colWidths=[3.5 * cm, None, 3.5 * cm])
        header_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (0, 0), "LEFT"),
                    ("ALIGN", (1, 0), (1, 0), "CENTER"),
                    ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )

        return [header_table, Spacer(1, 0.4 * cm)]

    def _criar_linha_unidade(self, unidade, cell_style, cell_style_center):
        return [
            Paragraph(str(unidade.codigo) if unidade.codigo else "-", cell_style_center),
            Paragraph(str(unidade.sigla) if unidade.sigla else "-", cell_style),
            Paragraph(str(unidade.nome) if unidade.nome else "-", cell_style),
            Paragraph(self.get_status_text(unidade), cell_style_center),
        ]

    def _criar_tabela_unidades(self, unidades):
        styles = getSampleStyleSheet()
        if not unidades:
            return [
                Paragraph(
                    self.get_empty_message(),
                    styles["Normal"],
                )
            ]

        cell_style, cell_style_center = self._criar_estilos_celula(styles)
        data = [["Código", "Sigla", "Nome", "Status"]]

        for unidade in unidades:
            data.append(self._criar_linha_unidade(unidade, cell_style, cell_style_center))

        table = Table(
            data,
            colWidths=self.get_table_col_widths(),
            repeatRows=1,
            splitByRow=True,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#149f67")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), self.TABLE_FONT_SIZE),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                    ("TOPPADDING", (0, 0), (-1, 0), 6),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), self.TABLE_FONT_SIZE),
                    ("VALIGN", (0, 1), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 1), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f8f9fa")],
                    ),
                ]
            )
        )

        return [table]

    def _adicionar_numero_pagina(self, canvas, doc):
        canvas.saveState()

        request = getattr(self, "_export_request", None)
        data_emissao = localtime(timezone.now()).strftime("%d/%m/%Y às %H:%M")
        usuario = self._resolver_usuario_exportacao(request)

        footer_text = f"Gerado por {usuario} em {data_emissao}"
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(0.5 * cm, 0.5 * cm, footer_text)
        canvas.drawCentredString(
            A4[0] / 2, 0.5 * cm, f"Página {canvas.getPageNumber()}"
        )
        canvas.restoreState()

    def is_binary(self):
        return True

    def get_read_mode(self):
        return "rb"

    def get_extension(self):
        return "pdf"

    def get_content_type(self):
        return "application/pdf"

    def can_import(self):
        return False

    def can_export(self):
        return True


class UnidadeAdministrativaPDFFormat(BaseUnidadePDFFormat):

    REPORT_TITLE = "Relatório de Unidades Administrativas"
    EMPTY_MESSAGE = (
        "<i>Nenhuma unidade administrativa encontrada com os filtros aplicados.</i>"
    )
    TABLE_COL_WIDTHS = [2 * cm, 5.5 * cm, 10 * cm, 2 * cm]

    def get_status_text(self, unidade):
        return unidade.get_status_display() if unidade.status else "-"


class UnidadeOrcamentariaPDFFormat(BaseUnidadePDFFormat):

    REPORT_TITLE = "Relatório de Unidades Orçamentárias"
    EMPTY_MESSAGE = (
        "<i>Nenhuma unidade orçamentária encontrada com os filtros aplicados.</i>"
    )
    TABLE_COL_WIDTHS = [3 * cm, 4 * cm, 10.5 * cm, 2.5 * cm]

    def get_status_text(self, unidade):
        return "Ativa" if unidade.ativa else "Inativa"
