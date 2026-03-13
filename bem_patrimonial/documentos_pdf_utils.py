from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import Table, TableStyle, Paragraph, Spacer

from bem_patrimonial.pdf_utils import (
    PDFConfigBase,
    criar_estilo_base,
    carregar_logo,
    formatar_moeda_brasileira,
    obter_nome_usuario,
    criar_info_geracao_paragraph,
)


def desenhar_tabela_no_canvas(canvas, doc, tabela, y_top):
    if not tabela:
        return

    tabela.wrapOn(canvas, doc.width, A4[1])
    tabela.drawOn(canvas, doc.leftMargin, y_top - tabela._height)


def desenhar_rodape_padrao(
    canvas,
    doc,
    tabela_rodape,
    usuario,
    data_geracao=None,
    config_cls=PDFConfigBase,
):
    y_base = 1.5 * cm
    page_num = canvas.getPageNumber()

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)
    canvas.drawRightString(A4[0] - doc.rightMargin, y_base + 0.2 * cm, f"Página {page_num}")

    if tabela_rodape:
        tabela_rodape.wrapOn(canvas, doc.width, A4[1])
        tabela_rodape.drawOn(canvas, doc.leftMargin, y_base + 0.8 * cm)

    info_elements = criar_info_geracao_paragraph(
        usuario=usuario,
        data_geracao=data_geracao,
        config_cls=config_cls,
    )
    if len(info_elements) > 1:
        info_para = info_elements[1]
        info_para.wrapOn(canvas, doc.width, A4[1])
        info_para.drawOn(canvas, doc.leftMargin, y_base + 0.2 * cm)


def criar_cabecalho_registro_documento(
    *,
    titulo_documento,
    titulo_registro,
    label_data_1,
    label_data_2,
    label_numero,
    valor_data_1,
    valor_data_2,
    valor_numero,
    config_cls=PDFConfigBase,
):
    styles = getSampleStyleSheet()

    title_style = criar_estilo_base(
        "CabecalhoTitulo",
        styles,
        config_cls=config_cls,
        fontSize=config_cls.FONTE_TITULO,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        spaceAfter=1,
        leading=9,
    )
    subtitle_style = criar_estilo_base(
        "CabecalhoSubtitulo",
        styles,
        config_cls=config_cls,
        fontSize=7,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        spaceAfter=1,
        leading=8,
    )
    desc_style = criar_estilo_base(
        "CabecalhoDesc",
        styles,
        config_cls=config_cls,
        fontSize=6,
        alignment=TA_CENTER,
        leading=7,
    )
    label_style = criar_estilo_base(
        "RegistroLabel",
        styles,
        config_cls=config_cls,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )
    value_style = criar_estilo_base(
        "RegistroValue",
        styles,
        config_cls=config_cls,
        fontSize=config_cls.FONTE_TITULO,
        alignment=TA_CENTER,
        leading=10,
    )

    header_data = [
        [
            carregar_logo(styles, config_cls=config_cls),
            [
                Spacer(1, 0.1 * cm),
                Paragraph("PREFEITURA MUNICIPAL DE SÃO PAULO", title_style),
                Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", subtitle_style),
                Paragraph(titulo_documento, desc_style),
                Spacer(1, 0.1 * cm),
            ],
        ]
    ]

    header_table = Table(
        header_data,
        colWidths=[2.5 * cm, 8.6 * cm],
        rowHeights=[2.0 * cm],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 1, colors.black),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )

    registro_data = [
        [Paragraph(titulo_registro, label_style), "", ""],
        [Paragraph("DATA", label_style), "", Paragraph(label_numero, label_style)],
        [Paragraph(label_data_1, label_style), Paragraph(label_data_2, label_style), ""],
        [
            Paragraph(valor_data_1, value_style),
            Paragraph(valor_data_2, value_style),
            Paragraph(valor_numero, value_style),
        ],
    ]

    registro_table = Table(
        registro_data,
        colWidths=[1.8 * cm, 1.8 * cm, 3.3 * cm],
        rowHeights=[0.55 * cm, 0.45 * cm, 0.45 * cm, 0.55 * cm],
    )
    registro_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (2, 0)),
                ("BACKGROUND", (0, 0), (2, 0), config_cls.COR_HEADER),
                ("FONTNAME", (0, 0), (2, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (2, 0), 8),
                ("SPAN", (0, 1), (1, 1)),
                ("BACKGROUND", (0, 1), (1, 1), config_cls.COR_CINZA_CLARO),
                ("BACKGROUND", (2, 1), (2, 1), config_cls.COR_CINZA_CLARO),
                ("SPAN", (2, 1), (2, 2)),
                ("BACKGROUND", (0, 2), (1, 2), config_cls.COR_CINZA_MEDIO),
                ("BACKGROUND", (0, 3), (2, 3), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 1, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )

    main_table = Table([[header_table, registro_table]], colWidths=[11.1 * cm, 6.9 * cm])
    main_table.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    return [main_table]


def criar_linha_ua_info(
    *,
    unidade_orcamentaria,
    label,
    sigla,
    nome,
    codigo,
    label_style,
    value_style,
):
    return [
        [
            Paragraph("<b>PREFIXO</b>", label_style),
            Paragraph(f"<b>{label}</b>", label_style),
            Paragraph("<b>CÓDIGO</b>", label_style),
        ],
        [
            Paragraph(str(sigla or "-").upper(), value_style),
            Paragraph(
                f"{str(unidade_orcamentaria or '-').upper()} / {str(nome or '-').upper()}",
                value_style,
            ),
            Paragraph(str(codigo or "-"), value_style),
        ],
    ]


def aplicar_estilo_tabela_info(info_table, linhas_cabecalho, config_cls=PDFConfigBase):
    estilos = []

    for linha in linhas_cabecalho:
        estilos.extend(
            [
                ("BACKGROUND", (0, linha), (2, linha), config_cls.COR_CINZA_CLARO),
                ("LINEABOVE", (0, linha), (-1, linha), 1, colors.grey),
            ]
        )

    for linha in range(max(linhas_cabecalho) + 2):
        if linha not in linhas_cabecalho:
            estilos.append(("BACKGROUND", (0, linha), (2, linha), colors.white))

    estilos.extend(
        [
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("BOX", (0, 0), (-1, -1), 1, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ]
    )
    info_table.setStyle(TableStyle(estilos))


def criar_tabela_bens_padrao(
    *,
    bens,
    descricao_fn,
    config_cls=PDFConfigBase,
):
    styles = getSampleStyleSheet()

    cell_style = criar_estilo_base(
        "CellStyle",
        styles,
        config_cls=config_cls,
        leading=8,
        wordWrap="CJK",
        alignment=TA_LEFT,
    )
    cell_style_center = criar_estilo_base(
        "CellStyleCenter",
        styles,
        config_cls=config_cls,
        leading=8,
        wordWrap="CJK",
        alignment=TA_CENTER,
    )
    header_style = criar_estilo_base(
        "HeaderStyle",
        styles,
        config_cls=config_cls,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )

    headers = [
        Paragraph("<b>NÚMERO DE CHAPA<br/>DE IDENTIFICAÇÃO</b>", header_style),
        Paragraph("<b>DISCRIMINAÇÃO</b>", header_style),
        Paragraph("<b>QUANTIDADE</b>", header_style),
        Paragraph("<b>VALOR<br/>UNITÁRIO</b>", header_style),
    ]

    data = [headers]

    for bem in bens:
        numero_pat = str(getattr(bem, "numero_patrimonial", None) or "-")
        descricao = descricao_fn(bem)
        valor_unitario = getattr(bem, "valor_unitario", None) or Decimal("0.00")

        data.append(
            [
                Paragraph(numero_pat, cell_style_center),
                Paragraph(descricao, cell_style),
                Paragraph("1", cell_style_center),
                Paragraph(formatar_moeda_brasileira(valor_unitario), cell_style_center),
            ]
        )

    bens_table = Table(
        data,
        colWidths=[
            config_cls.COL_NUMERO_CHAPA,
            config_cls.COL_DISCRIMINACAO,
            config_cls.COL_QUANTIDADE,
            config_cls.COL_VALOR,
        ],
        repeatRows=1,
    )
    bens_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), config_cls.COR_HEADER),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), config_cls.FONTE_PADRAO),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), config_cls.FONTE_PADRAO),
                ("ALIGN", (0, 1), (0, -1), "CENTER"),
                ("ALIGN", (2, 1), (3, -1), "CENTER"),
                ("VALIGN", (0, 1), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 1, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, config_cls.COR_CINZA_ZEBRA]),
            ]
        )
    )

    return [bens_table]


def criar_tabela_total_bens(*, bens, config_cls=PDFConfigBase):
    styles = getSampleStyleSheet()

    header_style = criar_estilo_base(
        "HeaderStyleTotal",
        styles,
        config_cls=config_cls,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )
    cell_style = criar_estilo_base(
        "CellStyleTotal",
        styles,
        config_cls=config_cls,
        leading=8,
        alignment=TA_LEFT,
    )

    quantidade_total = len(bens)
    valor_total_geral = sum((getattr(bem, "valor_unitario", None) or Decimal("0.00")) for bem in bens)

    total_data = [
        [
            Paragraph("", cell_style),
            Paragraph("<b>TOTAL GERAL</b>", header_style),
            Paragraph(f"<b>{quantidade_total}</b>", header_style),
            Paragraph(f"<b>{formatar_moeda_brasileira(valor_total_geral)}</b>", header_style),
        ]
    ]

    total_table = Table(
        total_data,
        colWidths=[
            config_cls.COL_NUMERO_CHAPA,
            config_cls.COL_DISCRIMINACAO,
            config_cls.COL_QUANTIDADE,
            config_cls.COL_VALOR,
        ],
    )
    total_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), config_cls.COR_CINZA_CLARO),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("ALIGN", (2, 0), (3, 0), "CENTER"),
                ("BOX", (0, 0), (-1, -1), 1, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    return [total_table]


def formatar_responsavel(usuario):
    if not usuario:
        return ""

    nome = obter_nome_usuario(usuario).upper()
    rf = getattr(usuario, "rf", None) or "-"
    return f"{nome} - RF: {rf}"


def criar_tabela_rodape_responsaveis(
    *,
    label_esquerda,
    label_direita,
    valor_esquerda,
    valor_direita,
    config_cls=PDFConfigBase,
):
    styles = getSampleStyleSheet()

    label_style = criar_estilo_base(
        "RodapeLabel",
        styles,
        config_cls=config_cls,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )
    value_style = criar_estilo_base(
        "RodapeValue",
        styles,
        config_cls=config_cls,
        alignment=TA_CENTER,
    )

    rodape_data = [
        [
            Paragraph(f"<b>{label_esquerda}</b>", label_style),
            Paragraph(f"<b>{label_direita}</b>", label_style),
        ],
        [
            Paragraph(valor_esquerda, value_style),
            Paragraph(valor_direita, value_style),
        ],
        [
            Paragraph("", value_style),
            Paragraph("", value_style),
        ],
    ]

    rodape_table = Table(
        rodape_data,
        colWidths=[9 * cm, 9 * cm],
        rowHeights=[0.5 * cm, 0.5 * cm, 1.2 * cm],
    )
    rodape_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (1, 0), config_cls.COR_HEADER),
                ("FONTNAME", (0, 0), (1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, 1), "MIDDLE"),
                ("VALIGN", (0, 2), (-1, 2), "BOTTOM"),
                ("BOX", (0, 0), (-1, -1), 1, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    return [rodape_table]
