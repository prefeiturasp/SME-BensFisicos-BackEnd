import os
import re
from io import BytesIO
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, IntegerField, Value
from django.db.models.functions import Cast, Substr, Replace
from django.utils import timezone
from django.http import HttpResponse

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

from bem_patrimonial.models import BaixaFisicaBemPatrimonial
from bem_patrimonial import constants
from bem_patrimonial.pdf_utils import (
    PDFConfigBase as PDFConfig,
    extrair_codigo_ua,
    formatar_moeda_brasileira,
    obter_nome_usuario,
    criar_estilo_base,
    carregar_logo,
    criar_info_geracao_paragraph,
)


def obter_bens_baixa(baixa):
    itens = baixa.itens.select_related("bem").all()
    bens = [item.bem for item in itens]
    return sorted(bens, key=lambda b: b.numero_patrimonial or "")


def gerar_numero_nbbpm(baixa):
    """
    Modelo alinhado ao CIMBPM: <COD_UA>.<SEQ_7>.<ANO>
    Ex: 287.0000001.2025
    """
    if not isinstance(baixa, BaixaFisicaBemPatrimonial):
        raise ValidationError("Objeto inválido para geração de NBBPM.")

    ano_baixa = baixa.data_baixa.year if baixa.data_baixa else timezone.localdate().year
    codigo_ua = extrair_codigo_ua(
        getattr(baixa.unidade_administrativa_origem, "codigo", "")
    )

    with transaction.atomic():
        qs = (
            BaixaFisicaBemPatrimonial.objects.select_for_update()
            .filter(
                numero_nbbpm__endswith=f".{ano_baixa}",
                numero_nbbpm__isnull=False,
            )
            .exclude(numero_nbbpm__exact="")
        )

        sequencial_raw = Substr("numero_nbbpm", 5, 7)

        sequencial_digits = Replace(sequencial_raw, Value("."), Value(""))

        ultimo_sequencial = qs.annotate(
            sequencial_int=Cast(sequencial_digits, IntegerField())
        ).aggregate(max_seq=Max("sequencial_int"))["max_seq"]

        numero_sequencial = (ultimo_sequencial or 0) + 1

    return f"{codigo_ua}.{numero_sequencial:07d}.{ano_baixa}"


def gerar_pdf_nbbpm(baixa, usuario_gerador=None, data_geracao=None):
    if not isinstance(baixa, BaixaFisicaBemPatrimonial):
        raise ValidationError("Objeto inválido para gerar NBBPM.")

    if baixa.status != constants.ACEITA:
        raise ValidationError(
            "Só é possível gerar NBBPM para Baixas Físicas aprovadas (ACEITA)."
        )

    if not getattr(baixa, "numero_nbbpm", None):
        baixa.numero_nbbpm = gerar_numero_nbbpm(baixa)
        baixa.save(update_fields=["numero_nbbpm"])

    buffer = BytesIO()

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PDFConfig.MARGEM_ESQUERDA,
        rightMargin=PDFConfig.MARGEM_DIREITA,
        topMargin=PDFConfig.MARGEM_SUPERIOR,
        bottomMargin=PDFConfig.MARGEM_INFERIOR,
        title=f"NBBPM {baixa.numero_nbbpm}",
        author="Sistema de Bens Físicos - SME",
    )

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")

    def on_page(canvas, doc_):
        canvas.saveState()
        _desenhar_cabecalho_em_pagina(canvas, doc_, baixa)
        _desenhar_rodape_em_pagina(canvas, doc_, baixa, usuario_gerador, data_geracao)
        canvas.restoreState()

    template = PageTemplate(id="todas_paginas", frames=[frame], onPage=on_page)
    doc.addPageTemplates([template])

    elements = []
    elements.extend(_criar_informacoes_gerais(baixa))
    elements.append(Spacer(1, 0.2 * cm))
    elements.extend(_criar_tabela_bens(baixa))
    elements.append(Spacer(1, 0.1 * cm))
    elements.extend(_criar_total_bens(baixa))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def _desenhar_cabecalho_em_pagina(canvas, doc, baixa):
    y_pos = A4[1] - 1.0 * cm
    header_elements = _criar_cabecalho_e_registro_nbbpm(baixa)

    if header_elements:
        header_table = header_elements[0]
        header_table.wrapOn(canvas, doc.width, A4[1])
        header_table.drawOn(canvas, doc.leftMargin, y_pos - header_table._height)


def _desenhar_rodape_em_pagina(
    canvas, doc, baixa, usuario_gerador=None, data_geracao=None
):
    y_base = 1.5 * cm
    page_num = canvas.getPageNumber()

    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.grey)
    canvas.drawRightString(
        A4[0] - doc.rightMargin, y_base + 0.2 * cm, f"Página {page_num}"
    )

    rodape_elements = _criar_rodape_nbbpm(baixa)
    if rodape_elements:
        rodape_table = rodape_elements[0]
        rodape_table.wrapOn(canvas, doc.width, A4[1])
        rodape_table.drawOn(canvas, doc.leftMargin, y_base + 0.8 * cm)

    usuario = usuario_gerador or getattr(baixa, "criado_por", None)
    info_elements = criar_info_geracao_paragraph(
        usuario=usuario,
        data_geracao=data_geracao,
        config_cls=PDFConfig,
    )
    if len(info_elements) > 1:
        info_para = info_elements[1]
        info_para.wrapOn(canvas, doc.width, A4[1])
        info_para.drawOn(canvas, doc.leftMargin, y_base + 0.2 * cm)


def _criar_cabecalho_e_registro_nbbpm(baixa):
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
        "CabecalhoDesc",
        styles,
        fontSize=6,
        alignment=TA_CENTER,
        leading=7,
    )
    label_style = criar_estilo_base(
        "RegistroLabel",
        styles,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )
    value_style = criar_estilo_base(
        "RegistroValue",
        styles,
        fontSize=PDFConfig.FONTE_TITULO,
        alignment=TA_CENTER,
        leading=10,
    )

    data_baixa = baixa.data_baixa.strftime("%d/%m/%Y") if baixa.data_baixa else ""
    data_aprov = (
        baixa.data_aprovacao.strftime("%d/%m/%Y") if baixa.data_aprovacao else ""
    )

    header_data = [
        [
            carregar_logo(styles),
            [
                Spacer(1, 0.1 * cm),
                Paragraph("PREFEITURA MUNICIPAL DE SÃO PAULO", title_style),
                Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", subtitle_style),
                Paragraph(
                    "NOTA DE BAIXA DE BENS PATRIMONIAIS MÓVEIS E INTANGÍVEIS (NBBPM)",
                    desc_style,
                ),
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
        [Paragraph("REGISTRO DA NBBPM", label_style), "", ""],
        [Paragraph("DATA", label_style), "", Paragraph("NÚMERO NBBPM", label_style)],
        [Paragraph("BAIXA", label_style), Paragraph("APROVAÇÃO", label_style), ""],
        [
            Paragraph(data_baixa, value_style),
            Paragraph(data_aprov, value_style),
            Paragraph(baixa.numero_nbbpm or "", value_style),
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

    return [main_table]


def _criar_linha_ua(unidade_ocrcamentaria, label, sigla, nome, codigo, label_style, value_style):

    return [
        [
            Paragraph("<b>PREFIXO</b>", label_style),
            Paragraph(f"<b>{label}</b>", label_style),
            Paragraph("<b>CÓDIGO</b>", label_style),
        ],
        [
            Paragraph((sigla or "-").upper(), value_style),
            Paragraph(f"{unidade_ocrcamentaria.upper()} / {nome.upper()}", value_style),
            Paragraph(str(codigo or "-"), value_style),
        ],
    ]


def _criar_informacoes_gerais(baixa):
    styles = getSampleStyleSheet()

    label_style = criar_estilo_base(
        "InfoLabel", styles, fontName="Helvetica-Bold", alignment=TA_LEFT
    )
    value_style = criar_estilo_base("InfoValue", styles, alignment=TA_LEFT)

    ua_origem = baixa.unidade_administrativa_origem

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
            ua_origem.unidade_orcamentaria.nome,
            "UNIDADE ORÇAMENTÁRIA / UNIDADE ADMINISTRATIVA (BAIXA)",
            getattr(ua_origem, "sigla", "-"),
            getattr(ua_origem, "nome", "-"),
            getattr(ua_origem, "codigo", "-"),
            label_style,
            value_style,
        )
    )

    info_data.extend(
        [
            [
                Paragraph("<b>NÚMERO DO PROCESSO DE BAIXA</b>", label_style),
                Paragraph("<b>DATA DA BAIXA</b>", label_style),
                Paragraph("<b>STATUS</b>", label_style),
            ],
            [
                Paragraph(str(baixa.numero_processo_baixa or "-").upper(), value_style),
                Paragraph(
                    (
                        baixa.data_baixa.strftime("%d/%m/%Y")
                        if baixa.data_baixa
                        else "-"
                    ),
                    value_style,
                ),
                Paragraph(
                    str(
                        baixa.get_status_display()
                        if hasattr(baixa, "get_status_display")
                        else baixa.status
                    ).upper(),
                    value_style,
                ),
            ],
        ]
    )

    info_table = Table(info_data, colWidths=[5.0 * cm, 10.0 * cm, 3.0 * cm])
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

    return [info_table]


def _criar_tabela_bens(baixa):
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
    bens = obter_bens_baixa(baixa)

    for bem in bens:
        numero_pat = bem.numero_patrimonial or "-"
        descricao = (bem.descricao or bem.nome or "-").upper()
        valor_unitario = bem.valor_unitario or Decimal("0.00")

        row = [
            Paragraph(str(numero_pat), cell_style_center),
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
                ("BACKGROUND", (0, 0), (-1, 0), PDFConfig.COR_HEADER),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), PDFConfig.FONTE_PADRAO),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), PDFConfig.FONTE_PADRAO),
                ("ALIGN", (0, 1), (0, -1), "CENTER"),
                ("ALIGN", (2, 1), (3, -1), "CENTER"),
                ("VALIGN", (0, 1), (-1, -1), "TOP"),
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

    return [bens_table]


def _criar_total_bens(baixa):
    styles = getSampleStyleSheet()

    header_style = criar_estilo_base(
        "HeaderStyleTotal", styles, fontName="Helvetica-Bold", alignment=TA_CENTER
    )
    cell_style = criar_estilo_base(
        "CellStyleTotal", styles, leading=8, alignment=TA_LEFT
    )

    bens = obter_bens_baixa(baixa)
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

    return [total_table]


def _criar_rodape_nbbpm(baixa):
    styles = getSampleStyleSheet()

    label_style = criar_estilo_base(
        "RodapeLabel", styles, fontName="Helvetica-Bold", alignment=TA_CENTER
    )
    value_style = criar_estilo_base("RodapeValue", styles, alignment=TA_CENTER)

    resp_baixa = getattr(baixa, "criado_por", None)
    nome_baixa = obter_nome_usuario(resp_baixa).upper()
    rf_baixa = getattr(resp_baixa, "rf", None) or "-"

    resp_aprov = getattr(baixa, "aprovado_por", None)
    if resp_aprov:
        nome_aprov = obter_nome_usuario(resp_aprov).upper()
        rf_aprov = getattr(resp_aprov, "rf", None) or "-"
        resp_aprov_txt = f"{nome_aprov} - RF: {rf_aprov}"
    else:
        resp_aprov_txt = ""

    rodape_data = [
        [
            Paragraph("<b>RESPONSÁVEL PELA BAIXA</b>", label_style),
            Paragraph("<b>RESPONSÁVEL PELA APROVAÇÃO</b>", label_style),
        ],
        [
            Paragraph(f"{nome_baixa} - RF: {rf_baixa}", value_style),
            Paragraph(resp_aprov_txt, value_style),
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

    return [rodape_table]


def http_response_nbbpm(baixa, usuario_gerador=None):
    buffer = gerar_pdf_nbbpm(baixa, usuario_gerador=usuario_gerador)
    filename = f"NBBPM_{baixa.numero_nbbpm}.pdf"

    resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
