from decimal import Decimal
from io import BytesIO

from django.core.exceptions import ValidationError
from django.http import HttpResponse

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Spacer,
    Paragraph,
    Table,
    TableStyle,
)

from bem_patrimonial.models import NBBPM
from bem_patrimonial.pdf_utils import (
    PDFConfigBase as PDFConfig,
    criar_estilo_base,
    formatar_moeda_brasileira,
    formatar_data,
)
from bem_patrimonial.documentos_pdf_utils import (
    criar_cabecalho_registro_documento,
    criar_tabela_rodape_responsaveis,
    desenhar_rodape_padrao,
    desenhar_tabela_no_canvas,
)

DATE_FMT_BR = "%d/%m/%Y"


def gerar_numero_nbbpm_lote(nbbpm):
    """Compatibilidade: delega ao serviço unificado (prefixo fixo 001, sequencial global por ano)."""
    from bem_patrimonial.services.nbbpm_numero import gerar_numero_nbbpm_unificado

    return gerar_numero_nbbpm_unificado(nbbpm)


def obter_bens_nbbpm_lote(nbbpm):
    """Bens de todas as Baixas vinculadas, ordenados por patrimônio."""
    bens = []
    for baixa in nbbpm.baixas.prefetch_related("itens__bem").all():
        for item in baixa.itens.select_related("bem").all():
            if item.bem:
                bens.append(item.bem)
    return sorted(bens, key=lambda b: b.numero_patrimonial or "")


def _criar_documento_nbbpm(buffer, nbbpm):
    return BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PDFConfig.MARGEM_ESQUERDA,
        rightMargin=PDFConfig.MARGEM_DIREITA,
        topMargin=PDFConfig.MARGEM_SUPERIOR,
        bottomMargin=PDFConfig.MARGEM_INFERIOR,
        title=f"NBBPM {nbbpm.numero}",
        author="Sistema de Bens Físicos - SME",
    )


def _montar_conteudo_nbbpm(nbbpm):
    elements = []
    elements.extend(_criar_informacoes_gerais(nbbpm))
    elements.append(Spacer(1, 0.2 * cm))
    elements.extend(_criar_tabela_bens(nbbpm))
    return elements


def _construir_pdf(nbbpm, usuario_gerador, data_geracao, total_paginas):
    buffer = BytesIO()
    doc = _criar_documento_nbbpm(buffer, nbbpm)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")

    def on_page(canvas, doc_):
        canvas.saveState()
        _desenhar_cabecalho_em_pagina(canvas, doc_, nbbpm)
        _desenhar_rodape_em_pagina(
            canvas,
            doc_,
            nbbpm,
            usuario_gerador=usuario_gerador,
            data_geracao=data_geracao,
            total_paginas=total_paginas,
        )
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="todas_paginas", frames=[frame], onPage=on_page)])
    doc.build(_montar_conteudo_nbbpm(nbbpm))
    buffer.seek(0)
    return buffer, doc.page


def gerar_pdf_nbbpm_lote(nbbpm, usuario_gerador=None, data_geracao=None):
    if not isinstance(nbbpm, NBBPM):
        raise ValidationError("Objeto inválido para gerar NBBPM.")

    if not nbbpm.numero:
        raise ValidationError("A NBBPM ainda não possui número gerado.")

    _, total_paginas = _construir_pdf(nbbpm, usuario_gerador, data_geracao, None)
    buffer, _ = _construir_pdf(nbbpm, usuario_gerador, data_geracao, total_paginas)
    return buffer


def _desenhar_cabecalho_em_pagina(canvas, doc, nbbpm):
    cabecalho = criar_cabecalho_registro_documento(
        titulo_documento="NOTA DE BAIXA DE BENS PATRIMONIAIS MÓVEIS E INTANGÍVEIS - NBBPM",
        titulo_registro="REGISTRO DA NBBPM",
        label_data_1="DATA",
        label_data_2="",
        label_numero="NÚMERO",
        valor_data_1=formatar_data(nbbpm.data_autorizacao),
        valor_data_2="",
        valor_numero=nbbpm.numero or "",
        config_cls=PDFConfig,
    )
    if cabecalho:
        desenhar_tabela_no_canvas(canvas, doc, cabecalho[0], A4[1] - 1.0 * cm)


def _desenhar_rodape_em_pagina(
    canvas, doc, nbbpm, usuario_gerador=None, data_geracao=None, total_paginas=None
):
    usuario = usuario_gerador or nbbpm.criado_por
    tabela_rodape = None
    if total_paginas is None or doc.page == total_paginas:
        tabela_rodape = _criar_rodape_nbbpm(nbbpm)[0]

    desenhar_rodape_padrao(
        canvas,
        doc,
        tabela_rodape,
        usuario=usuario,
        data_geracao=data_geracao,
        config_cls=PDFConfig,
    )


def _criar_rodape_nbbpm(nbbpm):
    _ = nbbpm
    return criar_tabela_rodape_responsaveis(
        label_esquerda="CONTADOR DA UNIDADE ORÇAMENTÁRIA",
        label_direita="TITULAR DA UNIDADE ORÇAMENTÁRIA",
        valor_esquerda="",
        valor_direita="",
        config_cls=PDFConfig,
        alturas_linhas=[0.5 * cm, 0.85 * cm, 0.85 * cm],
    )


def _criar_informacoes_gerais(nbbpm):
    styles = getSampleStyleSheet()

    label_style = criar_estilo_base(
        "NBBPMLoteLabel", styles, config_cls=PDFConfig,
        fontName="Helvetica-Bold", alignment=TA_LEFT,
    )
    value_style = criar_estilo_base(
        "NBBPMLoteValue", styles, config_cls=PDFConfig, alignment=TA_LEFT,
    )

    ua = nbbpm.unidade_administrativa_origem
    uo = nbbpm.unidade_orcamentaria

    destinacao = str(nbbpm.numero_processo_destinacao_final or "-").upper()

    uo_nome = str(getattr(uo, "nome", None) or getattr(ua, "nome", "-") or "-").upper()

    info_data = [
        [
            Paragraph("<b>PREFIXO</b>", label_style),
            Paragraph("<b>ÓRGÃO</b>", label_style),
            "",
            Paragraph("<b>CÓDIGO</b>", label_style),
        ],
        [
            Paragraph("SME", value_style),
            Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", value_style),
            "",
            Paragraph("16", value_style),
        ],
        [
            Paragraph("<b>PREFIXO</b>", label_style),
            Paragraph("<b>UNIDADE ORÇAMENTÁRIA</b>", label_style),
            "",
            Paragraph("<b>CÓDIGO</b>", label_style),
        ],
        [
            Paragraph(str(getattr(uo, "sigla", None) or getattr(ua, "sigla", "-") or "-").upper(), value_style),
            Paragraph(uo_nome, value_style),
            "",
            Paragraph(str(getattr(uo, "codigo", None) or getattr(ua, "codigo", "-") or "-"), value_style),
        ],
        [
            Paragraph("<b>Nº PROCESSO DE BAIXA</b>", label_style),
            Paragraph("<b>DATA DA AUTORIZAÇÃO</b>", label_style),
            Paragraph("<b>RESPONSÁVEL</b>", label_style),
            Paragraph("<b>Nº PROCESSO DE DESTINAÇÃO FINAL</b>", label_style),
        ],
        [
            Paragraph(str(nbbpm.numero_processo_baixa or "-").upper(), value_style),
            Paragraph(formatar_data(nbbpm.data_autorizacao) or "-", value_style),
            Paragraph(str(nbbpm.responsavel or "-").upper(), value_style),
            Paragraph(destinacao, value_style),
        ],
    ]

    info_table = Table(info_data, colWidths=[4.0 * cm, 3.0 * cm, 7.0 * cm, 4.0 * cm])

    estilos = [
        ("SPAN", (1, 0), (2, 0)),
        ("SPAN", (1, 1), (2, 1)),
        ("SPAN", (1, 2), (2, 2)),
        ("SPAN", (1, 3), (2, 3)),
        ("BACKGROUND", (0, 0), (3, 0), PDFConfig.COR_CINZA_CLARO),
        ("BACKGROUND", (0, 2), (3, 2), PDFConfig.COR_CINZA_CLARO),
        ("BACKGROUND", (0, 4), (3, 4), PDFConfig.COR_CINZA_CLARO),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
    ]

    info_table.setStyle(TableStyle(estilos))

    return [info_table]


def _criar_tabela_bens(nbbpm):
    bens = obter_bens_nbbpm_lote(nbbpm)
    styles = getSampleStyleSheet()

    header_style = criar_estilo_base(
        "NBBPMLoteHeader", styles, config_cls=PDFConfig,
        fontName="Helvetica-Bold", alignment=TA_CENTER,
    )
    cell_center = criar_estilo_base(
        "NBBPMLoteCellCenter", styles, config_cls=PDFConfig,
        alignment=TA_CENTER, leading=8, wordWrap="CJK",
    )
    cell_left = criar_estilo_base(
        "NBBPMLoteCellLeft", styles, config_cls=PDFConfig,
        alignment=TA_LEFT, leading=8, wordWrap="CJK",
    )

    col_widths = [2.5 * cm, 2.5 * cm, 6.2 * cm, 2.0 * cm, 2.4 * cm, 2.4 * cm]

    header_row_1 = [
        Paragraph("<b>NÚMERO DA CHAPA DE IDENTIFICAÇÃO</b>", header_style), "",
        Paragraph("<b>DISCRIMINAÇÃO</b>", header_style),
        Paragraph("<b>QUANTIDADE</b>", header_style),
        Paragraph("<b>VALOR</b>", header_style), "",
    ]
    header_row_2 = [
        Paragraph("<b>DE</b>", header_style),
        Paragraph("<b>ATÉ</b>", header_style),
        "", "",
        Paragraph("<b>UNITÁRIO</b>", header_style),
        Paragraph("<b>TOTAL</b>", header_style),
    ]

    data = [header_row_1, header_row_2]

    valor_total_geral = Decimal("0.00")

    for bem in bens:
        numero_pat = str(getattr(bem, "numero_patrimonial", None) or "-")
        descricao = str(getattr(bem, "nome", None) or getattr(bem, "descricao", None) or "-").upper()
        valor_unitario = getattr(bem, "valor_unitario", None) or Decimal("0.00")
        valor_total_geral += valor_unitario

        data.append(
            [
                Paragraph(numero_pat, cell_center),
                Paragraph(numero_pat, cell_center),
                Paragraph(descricao, cell_left),
                Paragraph("1", cell_center),
                Paragraph(formatar_moeda_brasileira(valor_unitario), cell_center),
                Paragraph(formatar_moeda_brasileira(valor_unitario), cell_center),
            ]
        )

    linha_total_idx = len(data)
    data.append(
        [
            "",
            "",
            Paragraph("<b>TOTAL GERAL</b>", header_style),
            Paragraph(f"<b>{len(bens)}</b>", header_style),
            "",
            Paragraph(f"<b>{formatar_moeda_brasileira(valor_total_geral)}</b>", header_style),
        ]
    )

    bens_table = Table(data, colWidths=col_widths, repeatRows=2)

    estilos = [
        ("SPAN", (0, 0), (1, 0)),
        ("SPAN", (2, 0), (2, 1)),
        ("SPAN", (3, 0), (3, 1)),
        ("SPAN", (4, 0), (5, 0)),
        ("BACKGROUND", (0, 0), (-1, 1), PDFConfig.COR_HEADER),
        ("BACKGROUND", (0, linha_total_idx), (-1, linha_total_idx), PDFConfig.COR_CINZA_CLARO),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), PDFConfig.FONTE_PADRAO),
        ("ALIGN", (0, 0), (-1, 1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 2), (1, linha_total_idx - 1), "CENTER"),
        ("ALIGN", (3, 2), (5, linha_total_idx - 1), "CENTER"),
        ("VALIGN", (0, 2), (-1, linha_total_idx - 1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 2), (-1, linha_total_idx - 1), [colors.white, PDFConfig.COR_CINZA_ZEBRA]),
        ("ALIGN", (2, linha_total_idx), (2, linha_total_idx), "RIGHT"),
    ]
    bens_table.setStyle(TableStyle(estilos))

    if not bens:
        return [Paragraph("<i>Nenhum bem vinculado às Baixas selecionadas.</i>", cell_left)]

    return [bens_table]


def http_response_nbbpm_lote(nbbpm, usuario_gerador=None):
    buffer = gerar_pdf_nbbpm_lote(nbbpm, usuario_gerador=usuario_gerador)
    filename = f"NBBPM_{nbbpm.numero}.pdf"

    resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
