# bem_patrimonial/laudo_avaliacao.py
#
# Gera o "Laudo de Avaliação para Baixa de Bens Patrimoniais Móveis"
# conforme Artigo 20 do Decreto 53.484/2012.
#
# Documento distinto da NBBPM (nbbpm.py):
#   - Sem número sequencial próprio
#   - Sem colunas de quantidade ou valor
#   - Com fundamentação legal do Decreto 53.484/2012
#   - Assinaturas de Operador de Inventário e Chefia Imediata
#   - Rodapé com data da SOLICITAÇÃO (data_criacao), não data de geração

from io import BytesIO

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from bem_patrimonial import constants
from bem_patrimonial.models import BaixaFisicaBemPatrimonial
from bem_patrimonial.pdf_utils import (
    PDFConfigBase as PDFConfig,
    carregar_logo,
    criar_estilo_base,
    obter_rf_usuario,
)

DATE_FMT_BR = "%d/%m/%Y"

# ---------------------------------------------------------------------------
# Largura útil da página
# ---------------------------------------------------------------------------
LARGURA_UTIL = A4[0] - PDFConfig.MARGEM_ESQUERDA - PDFConfig.MARGEM_DIREITA


# ===========================================================================
# HELPERS INTERNOS
# ===========================================================================

def _obter_bens_baixa(baixa: BaixaFisicaBemPatrimonial):
    """Retorna lista de bens ordenada por número patrimonial."""
    itens = baixa.itens.select_related("bem").all()
    bens = [item.bem for item in itens if item.bem]
    return sorted(bens, key=lambda b: b.numero_patrimonial or "")


def _formatar_data_criacao(baixa: BaixaFisicaBemPatrimonial) -> str:
    """
    Retorna a data de criação/solicitação da baixa no formato DD/MM/AAAA.
    Trata tanto datetime-aware quanto date simples.
    """
    dt = baixa.data_criacao
    if not dt:
        return "-"

    # Se for datetime, converte para date local
    if hasattr(dt, "date"):
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(PDFConfig.TZ_PADRAO)
            if timezone.is_aware(dt):
                dt = dt.astimezone(tz).date()
            else:
                dt = dt.date()
        except Exception:
            dt = dt.date()

    return dt.strftime(DATE_FMT_BR)


# ===========================================================================
# CABEÇALHO — desenhado no onPage para repetir em todas as páginas
# ===========================================================================

def _desenhar_cabecalho(canvas, _, baixa: BaixaFisicaBemPatrimonial):
    """
    Desenha o cabeçalho do laudo no topo de cada página:
      - Logo da SME (esquerda)
      - Texto institucional (centro/direita)
    """
    canvas.saveState()

    styles = getSampleStyleSheet()

    ua = baixa.unidade_administrativa_origem
    nome_ua = getattr(ua, "nome", "-") or "-"
    codigo_ua = getattr(ua, "codigo", "-") or "-"
    sigla_ua = getattr(ua, "sigla", "-") or "-"

    # Posição Y do topo (logo abaixo da margem superior)
    y_topo = A4[1] - 0.8 * cm

    # --- Logo ---
    # carregar_logo retorna Image (se arquivo existe) ou Paragraph (fallback "PMSP").
    # Ambos sao Flowables e precisam de wrap() antes de drawOn() —
    # sem isso o Paragraph explode com: AttributeError blPara
    logo = carregar_logo(styles, config_cls=PDFConfig, width_cm=2.2, height_cm=1.4)
    logo_x = PDFConfig.MARGEM_ESQUERDA
    logo_y = y_topo - 1.5 * cm
    logo_w = 2.2 * cm
    logo_h = 1.4 * cm

    try:
        logo.wrap(logo_w, logo_h)
        logo.drawOn(canvas, logo_x, logo_y)
    except Exception:
        # Ultimo recurso: escreve "PMSP" diretamente no canvas
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(logo_x, logo_y + 0.3 * cm, "PMSP")

    # --- Textos institucionais ---
    texto_x = PDFConfig.MARGEM_ESQUERDA + 2.8 * cm
    texto_largura = LARGURA_UTIL - 2.8 * cm

    estilo_inst = criar_estilo_base(
        "CabInst",
        styles,
        config_cls=PDFConfig,
        fontName="Helvetica-Bold",
        fontSize=8,
        alignment=TA_LEFT,
        leading=10,
    )
    estilo_ua = criar_estilo_base(
        "CabUA",
        styles,
        config_cls=PDFConfig,
        fontName="Helvetica",
        fontSize=7,
        alignment=TA_LEFT,
        leading=9,
    )

    linhas_texto = [
        Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", estilo_inst),
        Paragraph(nome_ua.upper(), estilo_ua),
        Paragraph(f"{codigo_ua} – {sigla_ua}", estilo_ua),
    ]

    y_texto = y_topo - 0.3 * cm
    for p in linhas_texto:
        _, h = p.wrap(texto_largura, 2 * cm)
        p.drawOn(canvas, texto_x, y_texto - h)
        y_texto -= h + 0.1 * cm

    # --- Linha separadora ---
    linha_y = y_topo - 1.9 * cm
    canvas.setStrokeColor(colors.black)
    canvas.setLineWidth(0.5)
    canvas.line(PDFConfig.MARGEM_ESQUERDA, linha_y, A4[0] - PDFConfig.MARGEM_DIREITA, linha_y)

    canvas.restoreState()


# ===========================================================================
# RODAPÉ — desenhado no onPage
# ===========================================================================

def _desenhar_rodape(canvas, _, baixa: BaixaFisicaBemPatrimonial):
    """
    Rodapé com identificação do solicitante e data da solicitação:
      "Solicitado por {RF} em DD/MM/AAAA"
    """
    canvas.saveState()

    styles = getSampleStyleSheet()
    estilo_rodape = criar_estilo_base(
        "Rodape",
        styles,
        config_cls=PDFConfig,
        fontSize=7,
        alignment=TA_CENTER,
        textColor=colors.grey,
    )

    rf = obter_rf_usuario(getattr(baixa, "criado_por", None))
    data_str = _formatar_data_criacao(baixa)
    texto = f"Solicitado por {rf} em {data_str}"

    p = Paragraph(texto, estilo_rodape)
    _, h = p.wrap(LARGURA_UTIL, 1 * cm)

    y_rodape = PDFConfig.MARGEM_INFERIOR - 1.0 * cm
    p.drawOn(canvas, PDFConfig.MARGEM_ESQUERDA, y_rodape)

    # Linha acima do rodapé
    canvas.setStrokeColor(colors.grey)
    canvas.setLineWidth(0.3)
    canvas.line(
        PDFConfig.MARGEM_ESQUERDA,
        y_rodape + h + 0.15 * cm,
        A4[0] - PDFConfig.MARGEM_DIREITA,
        y_rodape + h + 0.15 * cm,
    )

    canvas.restoreState()


# ===========================================================================
# ELEMENTOS DO CONTEÚDO
# ===========================================================================

def _criar_titulo(styles) -> list:
    """Título centralizado do documento."""
    estilo_titulo = criar_estilo_base(
        "LaudoTitulo",
        styles,
        config_cls=PDFConfig,
        fontName="Helvetica-Bold",
        fontSize=11,
        alignment=TA_CENTER,
        leading=14,
        spaceAfter=6,
    )
    return [
        Spacer(1, 0.4 * cm),
        Paragraph(
            "LAUDO DE AVALIAÇÃO PARA BAIXA DE BENS PATRIMONIAIS MÓVEIS",
            estilo_titulo,
        ),
        Spacer(1, 0.4 * cm),
    ]


def _criar_descricao_legal(styles) -> list:
    """
    Parágrafo de descrição (sublinhado+negrito) + citação legal em itálico.
    """
    estilo_desc = criar_estilo_base(
        "LaudoDesc",
        styles,
        config_cls=PDFConfig,
        fontSize=8,
        alignment=TA_JUSTIFY,
        leading=11,
        spaceAfter=4,
    )
    estilo_citacao = criar_estilo_base(
        "LaudoCitacao",
        styles,
        config_cls=PDFConfig,
        fontSize=8,
        alignment=TA_JUSTIFY,
        leading=11,
        leftIndent=0.5 * cm,
        spaceAfter=8,
    )

    descricao = (
        "<u><b>Atestamos que os Bens Patrimoniais Móveis abaixo indicados são "
        "Irrecuperáveis</b></u>, conforme Artigo 20 do Decreto 53.484/2012:"
    )
    citacao = (
        "<i>\" I – irrecuperável: quando não puder mais ser utilizado para o fim "
        "a que se destina devido à perda de suas características;\"</i>"
    )

    return [
        Paragraph(descricao, estilo_desc),
        Paragraph(citacao, estilo_citacao),
        Spacer(1, 0.3 * cm),
    ]


def _criar_tabela_bens(baixa: BaixaFisicaBemPatrimonial, styles) -> list:
    """
    Tabela de bens com apenas duas colunas:
      Nº Patrimonial / Empenho / Proc. Aquisição  |  Descrição do Bem
    Sem colunas de Quantidade ou Baixado Contabilmente.
    """
    bens = _obter_bens_baixa(baixa)

    estilo_header = criar_estilo_base(
        "TabelaHeader",
        styles,
        config_cls=PDFConfig,
        fontName="Helvetica-Bold",
        fontSize=8,
        alignment=TA_CENTER,
        leading=10,
    )
    estilo_celula = criar_estilo_base(
        "TabelaCelula",
        styles,
        config_cls=PDFConfig,
        fontSize=7,
        alignment=TA_LEFT,
        leading=9,
    )

    # Larguras: col patrimonial ~ 35%, descrição ~ 65%
    col_pat = LARGURA_UTIL * 0.35
    col_desc = LARGURA_UTIL * 0.65

    # Cabeçalho
    dados = [
        [
            Paragraph("Nº PATRIMONIAL /<br/>EMPENHO/<br/>PROC. AQUISIÇÃO", estilo_header),
            Paragraph("DESCRIÇÃO DO BEM", estilo_header),
        ]
    ]

    # Linhas de bens
    for bem in bens:
        numero = bem.numero_patrimonial or "-"
        descricao = (bem.descricao or bem.nome or "-").upper()
        dados.append([
            Paragraph(numero, estilo_celula),
            Paragraph(descricao, estilo_celula),
        ])

    if not bens:
        dados.append([
            Paragraph("-", estilo_celula),
            Paragraph("Nenhum bem vinculado.", estilo_celula),
        ])

    tabela = Table(dados, colWidths=[col_pat, col_desc], repeatRows=1)
    tabela.setStyle(TableStyle([
        # Cabeçalho
        ("BACKGROUND", (0, 0), (-1, 0), PDFConfig.COR_HEADER),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        # Bordas
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.grey),
        # Padding
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        # Zebra nas linhas de dados
        *[
            ("BACKGROUND", (0, i), (-1, i), PDFConfig.COR_CINZA_ZEBRA)
            for i in range(2, len(dados), 2)
        ],
    ]))

    return [tabela, Spacer(1, 0.6 * cm)]


def _criar_bloco_assinaturas(styles) -> list:
    """
    Duas células lado a lado para assinatura:
      Carimbo e assinatura do Operador de Inventário  |  Carimbo e assinatura Chefia Imediata
    """
    estilo_ass = criar_estilo_base(
        "Assinatura",
        styles,
        config_cls=PDFConfig,
        fontSize=7,
        alignment=TA_CENTER,
        leading=9,
    )

    largura_celula = LARGURA_UTIL / 2

    dados = [
        # Espaço em branco para a assinatura manuscrita
        ["", ""],
        # Linha de assinatura
        [
            Paragraph("_" * 45, estilo_ass),
            Paragraph("_" * 45, estilo_ass),
        ],
        # Labels
        [
            Paragraph("Carimbo e assinatura do Operador de Inventário", estilo_ass),
            Paragraph("Carimbo e assinatura Chefia Imediata", estilo_ass),
        ],
    ]

    tabela = Table(
        dados,
        colWidths=[largura_celula, largura_celula],
        rowHeights=[2.0 * cm, None, None],
    )
    tabela.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    return [Spacer(1, 1.0 * cm), tabela]


# ===========================================================================
# FUNÇÃO PRINCIPAL DE GERAÇÃO
# ===========================================================================

def gerar_pdf_laudo_avaliacao(
    baixa: BaixaFisicaBemPatrimonial,
) -> BytesIO:
    """
    Gera o Laudo de Avaliação para Baixa de Bens Patrimoniais Móveis em PDF.

    Args:
        baixa: Instância de BaixaFisicaBemPatrimonial com status ACEITA.

    Returns:
        BytesIO com o conteúdo do PDF pronto para download.

    Raises:
        ValidationError: Se o objeto não for válido ou status não for ACEITA.
    """
    if not isinstance(baixa, BaixaFisicaBemPatrimonial):
        raise ValidationError("Objeto inválido para gerar Laudo de Avaliação.")

    if baixa.status != constants.ACEITA:
        raise ValidationError(
            "O Laudo de Avaliação só pode ser gerado para Baixas Físicas aceitas."
        )

    buffer = BytesIO()

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PDFConfig.MARGEM_ESQUERDA,
        rightMargin=PDFConfig.MARGEM_DIREITA,
        # topMargin maior para acomodar o cabeçalho desenhado no canvas
        topMargin=PDFConfig.MARGEM_SUPERIOR + 0.5 * cm,
        bottomMargin=PDFConfig.MARGEM_INFERIOR,
        title="Laudo de Avaliação para Baixa de Bens Patrimoniais Móveis",
        author="Sistema de Bens Físicos - SME",
    )

    frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        doc.height,
        id="normal",
    )

    def on_page(canvas, doc_):
        _desenhar_cabecalho(canvas, doc_, baixa)
        _desenhar_rodape(canvas, doc_, baixa)

    template = PageTemplate(id="todas_paginas", frames=[frame], onPage=on_page)
    doc.addPageTemplates([template])

    styles = getSampleStyleSheet()

    elementos = []
    elementos.extend(_criar_titulo(styles))
    elementos.extend(_criar_descricao_legal(styles))
    elementos.extend(_criar_tabela_bens(baixa, styles))
    elementos.extend(_criar_bloco_assinaturas(styles))

    doc.build(elementos)
    buffer.seek(0)
    return buffer


# ===========================================================================
# HTTP RESPONSE HELPER
# ===========================================================================

def http_response_laudo_avaliacao(
    baixa: BaixaFisicaBemPatrimonial,
    usuario_gerador=None,  # NOSONAR
) -> HttpResponse:
    """
    Retorna HttpResponse com o PDF do Laudo de Avaliação pronto para download.
    """
    buffer = gerar_pdf_laudo_avaliacao(baixa)
    filename = f"Laudo-Avaliacao-{baixa.id}.pdf"

    resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
