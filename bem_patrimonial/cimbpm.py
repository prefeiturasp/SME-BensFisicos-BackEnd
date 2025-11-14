import os
import re
from io import BytesIO
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
    BaseDocTemplate,
    Frame,
    PageTemplate,
)
import pytz


class PDFConfig:
    MARGEM_ESQUERDA = 1.5 * cm
    MARGEM_DIREITA = 1.5 * cm
    MARGEM_SUPERIOR = 3.0 * cm
    MARGEM_INFERIOR = 4.5 * cm

    COL_NUMERO_CHAPA = 3.5 * cm
    COL_DISCRIMINACAO = 9.5 * cm
    COL_QUANTIDADE = 2 * cm
    COL_VALOR = 3 * cm

    COR_HEADER = colors.HexColor("#E0E0E0")
    COR_CINZA_CLARO = colors.HexColor("#F5F5F5")
    COR_CINZA_MEDIO = colors.HexColor("#F0F0F0")
    COR_CINZA_ZEBRA = colors.HexColor("#FAFAFA")

    FONTE_PADRAO = 7
    FONTE_TITULO = 8


def extrair_codigo_ua(codigo_completo):
    apenas_numeros = re.sub(r"\D", "", codigo_completo)

    if not apenas_numeros:
        return "000"

    if "." in codigo_completo:
        ultimo_grupo = codigo_completo.split(".")[-1]
        ultimo_numero = re.sub(r"\D", "", ultimo_grupo).lstrip("0") or "0"
    else:
        ultimo_numero = apenas_numeros.lstrip("0") or "0"

    return ultimo_numero.zfill(3)[-3:]


def formatar_moeda_brasileira(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def obter_bens_movimentacao(movimentacao):
    bens_itens = movimentacao.itens.select_related("bem").all()
    bens = [item.bem for item in bens_itens]

    # Fallback para compatibilidade com modelo antigo
    if not bens and movimentacao.bem_patrimonial:
        bens = [movimentacao.bem_patrimonial]

    return sorted(bens, key=lambda b: b.numero_patrimonial or "")


def obter_nome_usuario(usuario):
    return usuario.nome if usuario.nome else usuario.username


def criar_estilo_base(nome, parent, **kwargs):
    defaults = {
        "parent": parent["Normal"],
        "fontSize": PDFConfig.FONTE_PADRAO,
        "leading": 9,
    }
    defaults.update(kwargs)
    return ParagraphStyle(nome, **defaults)


def gerar_numero_cimbpm(movimentacao):
    from bem_patrimonial.models import MovimentacaoBemPatrimonial
    from django.db.models import Max
    from django.db.models.functions import Cast, Substr
    from django.db.models import IntegerField

    ano_movimentacao = movimentacao.criado_em.year
    codigo_origem = extrair_codigo_ua(movimentacao.unidade_administrativa_origem.codigo)
    codigo_destino = extrair_codigo_ua(
        movimentacao.unidade_administrativa_destino.codigo
    )

    with transaction.atomic():
        ultimo_sequencial = (
            MovimentacaoBemPatrimonial.objects.select_for_update()
            .filter(
                numero_cimbpm__endswith=f".{ano_movimentacao}",
                numero_cimbpm__isnull=False,
            )
            .annotate(
                sequencial_str=Substr("numero_cimbpm", 9, 7)
            )
            .aggregate(max_seq=Max(Cast("sequencial_str", IntegerField())))["max_seq"]
        )

        numero_sequencial = (ultimo_sequencial or 0) + 1

    return (
        f"{codigo_origem}.{codigo_destino}.{numero_sequencial:07d}.{ano_movimentacao}"
    )


def gerar_pdf_cimbpm(movimentacao, data_aceite=None):
    buffer = BytesIO()

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PDFConfig.MARGEM_ESQUERDA,
        rightMargin=PDFConfig.MARGEM_DIREITA,
        topMargin=PDFConfig.MARGEM_SUPERIOR,
        bottomMargin=PDFConfig.MARGEM_INFERIOR,
        title=f"CIMBPM {movimentacao.numero_cimbpm}",
        author="Sistema de Bens Físicos - SME",
    )

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")

    def on_page(canvas, doc):
        canvas.saveState()
        _desenhar_cabecalho_em_pagina(canvas, doc, movimentacao, data_aceite)
        _desenhar_rodape_em_pagina(canvas, doc, movimentacao, data_aceite)
        canvas.restoreState()

    template = PageTemplate(id="todas_paginas", frames=[frame], onPage=on_page)
    doc.addPageTemplates([template])

    elements = []
    elements.extend(_criar_informacoes_gerais(movimentacao))
    elements.append(Spacer(1, 0.2 * cm))
    elements.extend(_criar_tabela_bens(movimentacao))
    elements.append(Spacer(1, 0.1 * cm))
    elements.extend(_criar_total_bens(movimentacao))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def _desenhar_cabecalho_em_pagina(canvas, doc, movimentacao, data_aceite):
    y_pos = A4[1] - 1.0 * cm
    header_elements = _criar_cabecalho_e_registro_cimbpm(movimentacao, data_aceite)

    if header_elements:
        header_table = header_elements[0]
        header_table.wrapOn(canvas, doc.width, A4[1])
        header_table.drawOn(canvas, doc.leftMargin, y_pos - header_table._height)


def _desenhar_rodape_em_pagina(canvas, doc, movimentacao, data_aceite):
    y_base = 1.5 * cm
    page_num = canvas.getPageNumber()

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)
    canvas.drawRightString(
        A4[0] - doc.rightMargin, y_base + 0.2 * cm, f"Página {page_num}"
    )

    rodape_elements = _criar_rodape_cimbpm(movimentacao, data_aceite)
    if rodape_elements:
        rodape_table = rodape_elements[0]
        rodape_table.wrapOn(canvas, doc.width, A4[1])
        rodape_table.drawOn(canvas, doc.leftMargin, y_base + 0.8 * cm)

    info_elements = _criar_info_geracao(movimentacao)
    if len(info_elements) > 1:
        info_para = info_elements[1]
        info_para.wrapOn(canvas, doc.width, A4[1])
        info_para.drawOn(canvas, doc.leftMargin, y_base + 0.2 * cm)


def _carregar_logo(styles):
    static_root = settings.STATIC_ROOT or (
        settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else None
    )

    if static_root:
        logo_path = os.path.join(static_root, "img", "prefeitura_default_logo.png")
        if os.path.exists(logo_path):
            try:
                return Image(logo_path, width=2 * cm, height=2 * cm)
            except Exception:
                pass

    fallback_style = criar_estilo_base(
        "LogoFallback",
        styles,
        fontSize=9,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )
    return Paragraph("<b>PMSP</b>", fallback_style)


def _criar_cabecalho_e_registro_cimbpm(movimentacao, data_aceite):
    elements = []
    styles = getSampleStyleSheet()

    title_style = criar_estilo_base(
        "CabecalhoTitulo",
        styles,
        fontSize=PDFConfig.FONTE_TITULO,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        spaceAfter=1,
        leading=9,
    )
    subtitle_style = criar_estilo_base(
        "CabecalhoSubtitulo",
        styles,
        fontSize=7,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        spaceAfter=1,
        leading=8,
    )
    desc_style = criar_estilo_base(
        "CabecalhoDesc", styles, fontSize=6, alignment=TA_CENTER, leading=7
    )
    label_style = criar_estilo_base(
        "RegistroLabel", styles, fontName="Helvetica-Bold", alignment=TA_CENTER
    )
    value_style = criar_estilo_base(
        "RegistroValue",
        styles,
        fontSize=PDFConfig.FONTE_TITULO,
        alignment=TA_CENTER,
        leading=10,
    )

    data_emissao = (
        movimentacao.criado_em.strftime("%d/%m/%Y") if movimentacao.criado_em else ""
    )
    data_aceite_formatada = data_aceite.strftime("%d/%m/%Y") if data_aceite else ""

    header_data = [
        [
            _carregar_logo(styles),
            [
                Spacer(1, 0.1 * cm),
                Paragraph("PREFEITURA MUNICIPAL DE SÃO PAULO", title_style),
                Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", subtitle_style),
                Paragraph(
                    "CONTROLE INTERNO DA MOVIMENTAÇÃO DE BENS PATRIMONIAIS MÓVEIS E INTANGÍVEIS (CIMBPM)",
                    desc_style,
                ),
                Spacer(1, 0.1 * cm),
            ],
        ]
    ]

    header_table = Table(
        header_data, colWidths=[2.5 * cm, 8.6 * cm], rowHeights=[2.0 * cm]
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
        [Paragraph("REGISTRO DA CIMBPM", label_style), "", ""],
        [Paragraph("DATA", label_style), "", Paragraph("NÚMERO CIMBPM", label_style)],
        [Paragraph("EMISSÃO", label_style), Paragraph("ACEITE", label_style), ""],
        [
            Paragraph(data_emissao, value_style),
            Paragraph(data_aceite_formatada, value_style),
            Paragraph(movimentacao.numero_cimbpm or "", value_style),
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
                ("BACKGROUND", (0, 0), (2, 0), PDFConfig.COR_HEADER),
                ("FONTNAME", (0, 0), (2, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (2, 0), 8),
                ("SPAN", (0, 1), (1, 1)),
                ("BACKGROUND", (0, 1), (1, 1), PDFConfig.COR_CINZA_CLARO),
                ("BACKGROUND", (2, 1), (2, 1), PDFConfig.COR_CINZA_CLARO),
                ("SPAN", (2, 1), (2, 2)),
                ("BACKGROUND", (0, 2), (1, 2), PDFConfig.COR_CINZA_MEDIO),
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

    main_table = Table(
        [[header_table, registro_table]], colWidths=[11.1 * cm, 6.9 * cm]
    )
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

    elements.append(main_table)
    return elements


def _criar_linha_ua(label, sigla, nome, codigo, label_style, value_style):
    return [
        [
            Paragraph(f"<b>PREFIXO</b>", label_style),
            Paragraph(f"<b>{label}</b>", label_style),
            Paragraph(f"<b>CÓDIGO</b>", label_style),
        ],
        [
            Paragraph(sigla.upper(), value_style),
            Paragraph(nome.upper(), value_style),
            Paragraph(codigo, value_style),
        ],
    ]


def _criar_informacoes_gerais(movimentacao):
    elements = []
    styles = getSampleStyleSheet()

    label_style = criar_estilo_base(
        "InfoLabel", styles, fontName="Helvetica-Bold", alignment=TA_LEFT
    )
    value_style = criar_estilo_base("InfoValue", styles, alignment=TA_LEFT)

    ua_origem = movimentacao.unidade_administrativa_origem
    ua_destino = movimentacao.unidade_administrativa_destino

    info_data = [
        [
            Paragraph("<b>PREFIXO</b>", label_style),
            Paragraph("<b>ÓRGÃO</b>", label_style),
            Paragraph("<b>CÓDIGO</b>", label_style),
        ],
        [
            Paragraph("SME", value_style),
            Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", value_style),
            Paragraph("16", value_style),
        ],
    ]

    info_data.extend(
        _criar_linha_ua(
            "UNIDADE ORÇAMENTÁRIA / UNIDADE ADMINISTRATIVA QUE ENTREGA",
            ua_origem.sigla,
            ua_origem.nome,
            ua_origem.codigo,
            label_style,
            value_style,
        )
    )

    info_data.extend(
        _criar_linha_ua(
            "UNIDADE ORÇAMENTÁRIA / UNIDADE ADMINISTRATIVA QUE RECEBE",
            ua_destino.sigla,
            ua_destino.nome,
            ua_destino.codigo,
            label_style,
            value_style,
        )
    )

    info_table = Table(info_data, colWidths=[2.5 * cm, 12.5 * cm, 3 * cm])
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (2, 0), PDFConfig.COR_CINZA_CLARO),
                ("BACKGROUND", (0, 2), (2, 2), PDFConfig.COR_CINZA_CLARO),
                ("BACKGROUND", (0, 4), (2, 4), PDFConfig.COR_CINZA_CLARO),
                ("BACKGROUND", (0, 1), (2, 1), colors.white),
                ("BACKGROUND", (0, 3), (2, 3), colors.white),
                ("BACKGROUND", (0, 5), (2, 5), colors.white),
                ("LINEABOVE", (0, 0), (-1, 0), 1, colors.grey),
                ("LINEABOVE", (0, 2), (-1, 2), 1, colors.grey),
                ("LINEABOVE", (0, 4), (-1, 4), 1, colors.grey),
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
    )

    elements.append(info_table)
    return elements


def _criar_tabela_bens(movimentacao):
    elements = []
    styles = getSampleStyleSheet()

    cell_style = criar_estilo_base(
        "CellStyle", styles, leading=8, wordWrap="CJK", alignment=TA_LEFT
    )
    cell_style_center = criar_estilo_base(
        "CellStyleCenter", styles, leading=8, wordWrap="CJK", alignment=TA_CENTER
    )
    header_style = criar_estilo_base(
        "HeaderStyle", styles, fontName="Helvetica-Bold", alignment=TA_CENTER
    )

    headers = [
        Paragraph("<b>NÚMERO DE CHAPA<br/>DE IDENTIFICAÇÃO</b>", header_style),
        Paragraph("<b>DISCRIMINAÇÃO</b>", header_style),
        Paragraph("<b>QUANTIDADE</b>", header_style),
        Paragraph("<b>VALOR<br/>UNITÁRIO</b>", header_style),
    ]

    data = [headers]

    bens = obter_bens_movimentacao(movimentacao)

    for bem in bens:
        numero_pat = bem.numero_patrimonial or "-"
        descricao = bem.descricao.upper() if bem.descricao else "-"
        valor_unitario = bem.valor_unitario or Decimal("0.00")

        row = [
            Paragraph(numero_pat, cell_style_center),
            Paragraph(descricao, cell_style),
            Paragraph("1", cell_style_center),
            Paragraph(formatar_moeda_brasileira(valor_unitario), cell_style_center),
        ]
        data.append(row)

    bens_table = Table(
        data,
        colWidths=[
            PDFConfig.COL_NUMERO_CHAPA,
            PDFConfig.COL_DISCRIMINACAO,
            PDFConfig.COL_QUANTIDADE,
            PDFConfig.COL_VALOR,
        ],
        repeatRows=1,
    )
    bens_table.setStyle(
        TableStyle(
            [
                # Header
                ("BACKGROUND", (0, 0), (-1, 0), PDFConfig.COR_HEADER),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), PDFConfig.FONTE_PADRAO),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                # Corpo
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), PDFConfig.FONTE_PADRAO),
                ("ALIGN", (0, 1), (0, -1), "CENTER"),
                ("ALIGN", (2, 1), (3, -1), "CENTER"),
                ("VALIGN", (0, 1), (-1, -1), "TOP"),
                # Bordas e zebra
                ("BOX", (0, 0), (-1, -1), 1, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, PDFConfig.COR_CINZA_ZEBRA],
                ),
            ]
        )
    )

    elements.append(bens_table)
    return elements


def _criar_total_bens(movimentacao):
    elements = []
    styles = getSampleStyleSheet()

    header_style = criar_estilo_base(
        "HeaderStyle", styles, fontName="Helvetica-Bold", alignment=TA_CENTER
    )
    cell_style = criar_estilo_base("CellStyle", styles, leading=8, alignment=TA_LEFT)

    bens = obter_bens_movimentacao(movimentacao)

    quantidade_total = len(bens)
    valor_total_geral = sum((bem.valor_unitario or Decimal("0.00")) for bem in bens)

    total_data = [
        [
            Paragraph("", cell_style),
            Paragraph("<b>TOTAL GERAL</b>", header_style),
            Paragraph(f"<b>{quantidade_total}</b>", header_style),
            Paragraph(
                f"<b>{formatar_moeda_brasileira(valor_total_geral)}</b>", header_style
            ),
        ]
    ]

    total_table = Table(
        total_data,
        colWidths=[
            PDFConfig.COL_NUMERO_CHAPA,
            PDFConfig.COL_DISCRIMINACAO,
            PDFConfig.COL_QUANTIDADE,
            PDFConfig.COL_VALOR,
        ],
    )
    total_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PDFConfig.COR_CINZA_CLARO),
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

    elements.append(total_table)
    return elements


def _criar_rodape_cimbpm(movimentacao, data_aceite):
    elements = []
    styles = getSampleStyleSheet()

    label_style = criar_estilo_base(
        "RodapeLabel", styles, fontName="Helvetica-Bold", alignment=TA_CENTER
    )
    value_style = criar_estilo_base("RodapeValue", styles, alignment=TA_CENTER)

    responsavel_entrega = movimentacao.solicitado_por
    nome_entrega = obter_nome_usuario(responsavel_entrega).upper()
    rf_entrega = responsavel_entrega.rf if responsavel_entrega.rf else "-"

    responsavel_recebimento = ""
    if data_aceite and movimentacao.aprovado_por:
        responsavel_rec = movimentacao.aprovado_por
        nome_recebimento = obter_nome_usuario(responsavel_rec).upper()
        rf_recebimento = responsavel_rec.rf if responsavel_rec.rf else "-"
        responsavel_recebimento = f"{nome_recebimento} - RF: {rf_recebimento}"

    rodape_data = [
        [
            Paragraph("<b>RESPONSÁVEL PELA ENTREGA</b>", label_style),
            Paragraph("<b>RESPONSÁVEL PELO RECEBIMENTO</b>", label_style),
        ],
        [
            Paragraph(f"{nome_entrega} - RF: {rf_entrega}", value_style),
            Paragraph(responsavel_recebimento, value_style),
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
                ("BACKGROUND", (0, 0), (1, 0), PDFConfig.COR_HEADER),
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

    elements.append(rodape_table)
    return elements


def _criar_info_geracao(movimentacao):
    elements = []
    styles = getSampleStyleSheet()

    info_style = criar_estilo_base(
        "InfoGeracao", styles, alignment=TA_LEFT, textColor=colors.grey
    )

    tz_sp = pytz.timezone("America/Sao_Paulo")
    data_geracao = timezone.now().astimezone(tz_sp).strftime("%d/%m/%Y às %H:%M")
    nome_usuario = obter_nome_usuario(movimentacao.solicitado_por)

    info_text = f"Gerado por {nome_usuario} em {data_geracao}"
    elements.append(Spacer(1, 0.2 * cm))
    elements.append(Paragraph(info_text, info_style))

    return elements
