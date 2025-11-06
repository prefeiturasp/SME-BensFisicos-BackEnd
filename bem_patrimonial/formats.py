import os
from decimal import Decimal
from io import BytesIO
from django.conf import settings
from django.utils import timezone
from import_export.formats.base_formats import Format
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
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
    KeepTogether,
)


class PDFFormat(Format):

    def get_title(self):
        return "pdf"

    def create_dataset(self, in_stream):
        raise NotImplementedError("Importação não é suportada para PDF.")

    def export_data(self, dataset, **kwargs):
        request = getattr(self, "_export_request", None)
        queryset = getattr(self, "_export_queryset", None)

        bens_list = list(queryset) if queryset is not None else []

        total_registros = len(bens_list)

        valor_total = sum(bem.valor_unitario or Decimal("0.00") for bem in bens_list)
        localizacoes_unicas = len(
            set(bem.localizacao for bem in bens_list if bem.localizacao)
        )

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=0.3 * cm,
            rightMargin=0.3 * cm,
            topMargin=0.9 * cm,
            bottomMargin=0.9 * cm,
            title="Relatório de Bens Patrimoniais",
            author=(
                request.user.get_full_name() or request.user.username
                if request
                else "Sistema Bens Físicos"
            ),
        )

        elements = []
        elements.extend(self._criar_cabecalho(request))
        elements.extend(self._criar_info_relatorio(request, total_registros))
        elements.extend(self._criar_tabela_bens(bens_list))

        if bens_list:
            elements.extend(
                self._criar_resumo(total_registros, valor_total, localizacoes_unicas)
            )

        elements.extend(self._criar_rodape())

        doc.build(
            elements,
            onFirstPage=self._adicionar_numero_pagina,
            onLaterPages=self._adicionar_numero_pagina,
        )

        pdf_bytes = buffer.getvalue()
        buffer.close()

        return pdf_bytes

    def _criar_cabecalho(self, request):
        elements = []
        styles = getSampleStyleSheet()

        def _carregar_logo(filename, fallback_text):
            static_root = settings.STATIC_ROOT or (
                settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else None
            )
            if static_root:
                logo_path = os.path.join(static_root, "img", filename)
                if os.path.exists(logo_path):
                    try:
                        return Image(logo_path, width=3 * cm, height=1.5 * cm)
                    except:
                        pass
            return Paragraph(fallback_text, styles["Heading1"])

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
            _carregar_logo("bens_default_logo.png", "SME"),
            [
                Paragraph("Relatório de Bens Patrimoniais", title_style),
                Paragraph(
                    "Secretaria Municipal de Educação - Prefeitura de São Paulo",
                    subtitle_style,
                ),
            ],
            _carregar_logo("prefeitura_default_logo.png", "PMSP"),
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

        elements.append(header_table)
        elements.append(Spacer(1, 0.4 * cm))

        return elements

    def _criar_info_relatorio(self, request, total_registros):
        elements = []

        from django.utils.timezone import localtime

        data_geracao = localtime(timezone.now()).strftime("%d/%m/%Y às %H:%M")
        usuario = "Sistema"
        if (
            request
            and hasattr(request, "user")
            and request.user
            and request.user.is_authenticated
        ):
            user = request.user

            if hasattr(user, "nome") and user.nome:
                usuario = user.nome
            else:
                full_name = (
                    user.get_full_name() if hasattr(user, "get_full_name") else ""
                )
                usuario = (
                    full_name.strip()
                    if full_name and full_name.strip()
                    else user.username
                )

        info_data = [
            [
                "Data de Geração:",
                data_geracao,
                "Gerado por:",
                usuario,
                "Total de Registros:",
                str(total_registros),
            ],
        ]

        info_table = Table(
            info_data, colWidths=[3 * cm, 4.5 * cm, 2.5 * cm, 5 * cm, 3.5 * cm, 2 * cm]
        )
        info_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#333333")),
                    ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, 0), "Helvetica-Bold"),
                    ("FONTNAME", (4, 0), (4, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#149f67")),
                ]
            )
        )

        elements.append(info_table)
        elements.append(Spacer(1, 0.3 * cm))

        return elements

    def _criar_tabela_bens(self, bens_list):
        elements = []
        styles = getSampleStyleSheet()

        if not bens_list:
            empty_msg = Paragraph(
                "<i>Nenhum bem patrimonial encontrado com os filtros aplicados.</i>",
                styles["Normal"],
            )
            elements.append(empty_msg)
            return elements

        headers = [
            "Nº Patrimonial",
            "Nome",
            "Descrição",
            "Marca",
            "Modelo",
            "Localização",
            "Valor Unit. (R$)",
            "Nº Processo",
            "Unidade Administrativa",
        ]

        cell_style = ParagraphStyle(
            "CellStyle",
            parent=styles["Normal"],
            fontSize=7,
            leading=8,
            wordWrap="CJK",
        )

        data = [headers]

        for bem in bens_list:
            valor = f"{bem.valor_unitario:.2f}" if bem.valor_unitario else "-"
            numero_patrimonial = Paragraph(
                str(bem.numero_patrimonial) if bem.numero_patrimonial else "-",
                cell_style,
            )
            nome = Paragraph(str(bem.nome) if bem.nome else "-", cell_style)
            descricao = Paragraph(
                str(bem.descricao) if bem.descricao else "-", cell_style
            )
            marca = Paragraph(str(bem.marca) if bem.marca else "-", cell_style)
            modelo = Paragraph(str(bem.modelo) if bem.modelo else "-", cell_style)
            localizacao = Paragraph(
                str(bem.localizacao) if bem.localizacao else "-", cell_style
            )
            processo = Paragraph(
                str(bem.numero_processo) if bem.numero_processo else "-", cell_style
            )

            unidade_adm_text = "-"
            if bem.unidade_administrativa:
                unidade_adm_text = str(bem.unidade_administrativa.nome)
            unidade_administrativa = Paragraph(unidade_adm_text, cell_style)

            row = [
                numero_patrimonial,
                nome,
                descricao,
                marca,
                modelo,
                localizacao,
                valor,
                processo,
                unidade_administrativa,
            ]

            data.append(row)

        col_widths = [
            2.3 * cm,  # Nº Patrimonial
            3.5 * cm,  # Nome
            5.0 * cm,  # Descrição
            2.2 * cm,  # Marca
            2.2 * cm,  # Modelo
            2.2 * cm,  # Localização
            2.0 * cm,  # Valor Unit.
            2.0 * cm,  # Nº Processo
            4.0 * cm,  # Unidade Adm.
        ]

        # Permite que linhas se expandam automaticamente conforme conteúdo
        table = Table(data, colWidths=col_widths, repeatRows=1, splitByRow=True)

        table_style = TableStyle(
            [
                # Cabeçalho
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#149f67")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                # Corpo da tabela
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 7),
                ("ALIGN", (6, 1), (6, -1), "CENTER"),
                ("ALIGN", (7, 1), (7, -1), "RIGHT"),
                (
                    "VALIGN",
                    (0, 1),
                    (-1, -1),
                    "TOP",
                ),
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

        table.setStyle(table_style)
        elements.append(table)

        return elements

    def _criar_resumo(self, total_registros, valor_total, localizacoes_unicas):
        elements = []

        summary_data = [
            [
                "Total de Bens",
                "Valor Total (R$)",
                "Localizações Únicas",
            ],
            [
                str(total_registros),
                f"{valor_total:,.2f}".replace(",", "X")
                .replace(".", ",")
                .replace("X", "."),
                str(localizacoes_unicas),
            ],
        ]

        summary_table = Table(summary_data, colWidths=[None, None, None, None])
        summary_table.setStyle(
            TableStyle(
                [
                    # Cabeçalho
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#149f67")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 9),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    # Valores
                    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#e8f5e9")),
                    ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#149f67")),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 1), (-1, 1), 12),
                    ("ALIGN", (0, 1), (-1, 1), "CENTER"),
                    # Geral
                    ("BOX", (0, 0), (-1, -1), 1.5, colors.HexColor("#149f67")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#149f67")),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )

        # Agrupa Spacer e tabela para garantir que não sejam separados em páginas diferentes
        elements.append(KeepTogether([Spacer(1, 0.5 * cm), summary_table]))

        return elements

    def _adicionar_numero_pagina(self, canvas, doc):
        canvas.saveState()

        page_num = canvas.getPageNumber()
        text = f"Página {page_num}"

        canvas.setFont("Helvetica", 9)
        canvas.drawCentredString(
            landscape(A4)[0] / 2,
            0.5 * cm,
            text,
        )

        canvas.restoreState()

    def _criar_rodape(self):
        elements = []
        elements.append(Spacer(1, 0.5 * cm))

        return elements

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
