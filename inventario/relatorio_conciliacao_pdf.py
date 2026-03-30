import os
from io import BytesIO
from decimal import Decimal
from reportlab.pdfgen import canvas

from django.conf import settings
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
    KeepTogether,
)
import pytz

from inventario import constants as inv_constants
from bem_patrimonial.pdf_utils import obter_rf_usuario


class PDFConfig:
    MARGEM_ESQUERDA = 1.5 * cm
    MARGEM_DIREITA = 1.5 * cm
    MARGEM_SUPERIOR = 3.0 * cm
    MARGEM_INFERIOR = 4.5 * cm

    COR_HEADER = colors.HexColor("#E0E0E0")
    COR_CINZA_CLARO = colors.HexColor("#F5F5F5")
    COR_CINZA_MEDIO = colors.HexColor("#F0F0F0")
    COR_CINZA_ZEBRA = colors.HexColor("#FAFAFA")

    FONTE_PADRAO = 7
    FONTE_TITULO = 8


def criar_estilo_base(nome, parent, **kwargs):
    defaults = {
        "parent": parent["Normal"],
        "fontSize": PDFConfig.FONTE_PADRAO,
        "leading": 9,
    }
    defaults.update(kwargs)
    return ParagraphStyle(nome, **defaults)


def formatar_moeda_brasileira(valor):
    if valor is None:
        valor = Decimal("0.00")
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def obter_nome_usuario(usuario):

    if not usuario:
        return "-"
    return usuario.nome if getattr(usuario, "nome", None) else usuario.username


STATUS_NAO_CONCILIADO = "Não Conciliado"


def formatar_status_para_header(conciliacao):
    """
    Retorna o texto de STATUS adequado para o cabeçalho do PDF.
    """
    status_display = conciliacao.get_status_display()

    if STATUS_NAO_CONCILIADO in status_display:
        return STATUS_NAO_CONCILIADO

    return status_display


def _fmt_date(d):
    if not d:
        return "-"
    try:
        if hasattr(d, "strftime"):
            return d.strftime("%d/%m/%Y")
        return str(d)
    except Exception:
        return str(d)


def _carregar_logo(styles):
    static_root = settings.STATIC_ROOT or (
        settings.STATICFILES_DIRS[0] if settings.STATICFILES_DIRS else None
    )

    if static_root:
        logo_path = os.path.join(static_root, "img", "prefeitura_default_logo.png")
        if os.path.exists(logo_path):
            try:
                return Image(logo_path, width=2 * cm, height=1.3 * cm)
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


def _quebrar_texto_longo(txt, max_chars=180):
    """
    Não é obrigatório, mas ajuda a quebrar textos enormes sem ficar uma linha infinita.
    ReportLab quebra por espaços, mas aqui a gente força um pouco mais limpo.
    """
    if not txt:
        return "-"
    txt = str(txt).strip()
    if len(txt) <= max_chars:
        return txt
    return txt[:max_chars] + "..."


def _criar_info_geracao(usuario_gerador=None, data_geracao=None):
    elements = []
    styles = getSampleStyleSheet()

    info_style = criar_estilo_base(
        "InfoGeracao", styles, alignment=TA_LEFT, textColor=colors.grey
    )

    tz_sp = pytz.timezone("America/Sao_Paulo")

    data_ref = data_geracao or timezone.now()
    if timezone.is_naive(data_ref):
        data_ref = timezone.make_aware(data_ref)

    data_geracao_str = data_ref.astimezone(tz_sp).strftime("%d/%m/%Y às %H:%M")
    rf_usuario = obter_rf_usuario(usuario_gerador)

    info_text = f"Gerado por {rf_usuario} em {data_geracao_str}"
    elements.append(Paragraph(info_text, info_style))
    return elements


def _criar_cabecalho_e_registro_conciliacao(conciliacao, data_emissao):
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
        "RegistroLabel",
        styles,
        fontName="Helvetica-Bold",
        fontSize=7,
        alignment=TA_CENTER,
    )
    value_style = criar_estilo_base(
        "RegistroValue",
        styles,
        fontSize=7,
        alignment=TA_CENTER,
        leading=10,
    )

    data_emissao_str = data_emissao.strftime("%d/%m/%Y") if data_emissao else ""
    periodo_final_str = _fmt_date(conciliacao.periodo_final)
    numero_conciliacao = conciliacao.numero_conciliacao or ""
    tipo = conciliacao.get_tipo_display()
    status = formatar_status_para_header(conciliacao)

    header_data = [
        [
            _carregar_logo(styles),
            [
                Spacer(1, 0.1 * cm),
                Paragraph("PREFEITURA MUNICIPAL DE SÃO PAULO", title_style),
                Paragraph("SECRETARIA MUNICIPAL DE EDUCAÇÃO", subtitle_style),
                Paragraph(
                    "INVENTÁRIO ANUAL - RELATÓRIO DE CAMPO - FÍSICO (CONCILIAÇÃO)",
                    desc_style,
                ),
                Spacer(1, 0.1 * cm),
            ],
        ]
    ]

    header_table = Table(
        header_data, colWidths=[2.5 * cm, 8.6 * cm], rowHeights=[2.1 * cm]
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
        [Paragraph("REGISTRO DA CONCILIAÇÃO", label_style), "", ""],
        [
            Paragraph("DATA EMISSÃO", label_style),
            Paragraph("PERÍODO FINAL", label_style),
            Paragraph("Nº CONCILIAÇÃO", label_style),
        ],
        [
            Paragraph(data_emissao_str, value_style),
            Paragraph(periodo_final_str, value_style),
            Paragraph(numero_conciliacao, value_style),
        ],
        [Paragraph(f"TIPO: {tipo}  •  STATUS: {status}", label_style), "", ""],
    ]

    registro_table = Table(
        registro_data,
        colWidths=[2.2 * cm, 2.2 * cm, 2.5 * cm],
        rowHeights=[0.55 * cm, 0.45 * cm, 0.55 * cm, 0.55 * cm],
    )

    registro_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (2, 0)),
                ("BACKGROUND", (0, 0), (2, 0), PDFConfig.COR_HEADER),
                ("FONTNAME", (0, 0), (2, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (2, 0), 8),
                ("BACKGROUND", (0, 1), (2, 1), PDFConfig.COR_CINZA_CLARO),
                ("BACKGROUND", (0, 2), (2, 2), PDFConfig.COR_CINZA_MEDIO),
                ("SPAN", (0, 3), (2, 3)),
                ("BACKGROUND", (0, 3), (2, 3), PDFConfig.COR_CINZA_CLARO),
                ("FONTNAME", (0, 3), (2, 3), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BOX", (0, 0), (-1, -1), 1, colors.black),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 3), (2, 3), 0.5),
                ("BOTTOMPADDING", (0, 3), (2, 3), 0.5),
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


def _desenhar_cabecalho_em_pagina(canvas, doc, conciliacao, data_emissao):
    y_pos = A4[1] - 1.0 * cm
    header_elements = _criar_cabecalho_e_registro_conciliacao(conciliacao, data_emissao)
    if header_elements:
        header_table = header_elements[0]
        header_table.wrapOn(canvas, doc.width, A4[1])
        header_table.drawOn(canvas, doc.leftMargin, y_pos - header_table._height)


def _criar_rodape_conciliacao(conciliacao, usuario_gerador=None):
    elements = []
    styles = getSampleStyleSheet()

    label_style = criar_estilo_base(
        "RodapeLabel", styles, fontName="Helvetica-Bold", alignment=TA_CENTER
    )
    value_style = criar_estilo_base("RodapeValue", styles, alignment=TA_CENTER)

    criado_por = conciliacao.criado_por
    fechado_por = conciliacao.fechado_por

    responsavel_operacao = usuario_gerador or criado_por
    rf_operacao = obter_rf_usuario(responsavel_operacao)

    status_display = conciliacao.get_status_display()

    if STATUS_NAO_CONCILIADO in status_display:
        nome_fechamento = status_display
    elif fechado_por:
        nome_fechamento = obter_rf_usuario(fechado_por)
    else:
        nome_fechamento = ""

    rodape_data = [
        [
            Paragraph("<b>RESPONSÁVEL (EXPORTAÇÃO)</b>", label_style),
            Paragraph("<b>RESPONSÁVEL (FECHAMENTO)</b>", label_style),
        ],
        [
            Paragraph(rf_operacao, value_style),
            Paragraph(nome_fechamento, value_style),
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


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(num_pages)
            super().showPage()
        super().save()

    def _draw_page_number(self, page_count):
        page_num = self.getPageNumber()

        y = 1.5 * cm + 0.2 * cm

        x = self._pagesize[0] - PDFConfig.MARGEM_DIREITA

        self.setFont("Helvetica", 6)
        self.setFillColor(colors.grey)

        self.drawRightString(x, y, f"{page_num}/{page_count}")


def _desenhar_rodape_em_pagina(
    canvas, doc, conciliacao, usuario_gerador=None, data_geracao=None
):
    y_base = 1.5 * cm

    rodape_elements = _criar_rodape_conciliacao(conciliacao, usuario_gerador)
    if rodape_elements:
        rodape_table = rodape_elements[0]
        rodape_table.wrapOn(canvas, doc.width, A4[1])
        rodape_table.drawOn(canvas, doc.leftMargin, y_base + 0.8 * cm)

    info_elements = _criar_info_geracao(usuario_gerador, data_geracao)
    if info_elements:
        info_para = info_elements[0]
        info_para.wrapOn(canvas, doc.width, A4[1])
        info_para.drawOn(canvas, doc.leftMargin, y_base + 0.2 * cm)


def _criar_informacoes_gerais_conciliacao(conciliacao):
    """
    Mantém a estrutura de caixas/cores/linhas do CIMBPM,
    porém adaptada para conciliação (UA única).
    """
    elements = []
    styles = getSampleStyleSheet()

    label_style = criar_estilo_base(
        "InfoLabel", styles, fontName="Helvetica-Bold", alignment=TA_LEFT
    )
    value_style = criar_estilo_base("InfoValue", styles, alignment=TA_LEFT)

    ua = conciliacao.unidade_administrativa

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
        [
            Paragraph("<b>NOME</b>", label_style),
            Paragraph(
                "<b>UNIDADE ORÇAMENTÁRIA / UNIDADE ADMINISTRATIVA</b>", label_style
            ),
            Paragraph("<b>CÓDIGO</b>", label_style),
        ],
        [
            Paragraph((ua.sigla or "-").upper(), value_style),
            Paragraph(
                f"{ua.unidade_orcamentaria.nome} / {ua.nome }".upper(), value_style
            ),
            Paragraph((ua.codigo or "-"), value_style),
        ],
    ]

    info_table = Table(info_data, colWidths=[4.0 * cm, 11.0 * cm, 3.0 * cm])
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (2, 0), PDFConfig.COR_CINZA_CLARO),
                ("BACKGROUND", (0, 2), (2, 2), PDFConfig.COR_CINZA_CLARO),
                ("BACKGROUND", (0, 1), (2, 1), colors.white),
                ("BACKGROUND", (0, 3), (2, 3), colors.white),
                ("LINEABOVE", (0, 0), (-1, 0), 1, colors.grey),
                ("LINEABOVE", (0, 2), (-1, 2), 1, colors.grey),
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


def _estilos_blocos_itens(styles):
    """Cria estilos usados nos blocos de itens da conciliação."""
    font = 6
    leading = 7
    _ = criar_estilo_base(
        "ItemLabel",
        styles,
        fontName="Helvetica-Bold",
        fontSize=font,
        leading=leading,
        alignment=TA_LEFT,
    )
    txt = criar_estilo_base(
        "ItemText",
        styles,
        fontSize=font,
        leading=leading,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    txt_center = criar_estilo_base(
        "ItemTextCenter",
        styles,
        fontSize=font,
        leading=leading,
        alignment=TA_CENTER,
        wordWrap="CJK",
    )
    titulo_grupo = criar_estilo_base(
        "GrupoTitulo",
        styles,
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=8,
        alignment=TA_LEFT,
    )
    return {"txt": txt, "txt_center": txt_center, "titulo_grupo": titulo_grupo}


def _classificar_itens_conciliacao(itens):
    """Separa itens em: encontrados sem ocorrência e com ocorrência."""
    encontrados_sem_ocorrencia = []
    com_ocorrencia = []
    for item in itens:
        if item.tem_ocorrencia:
            com_ocorrencia.append(item)
        else:
            encontrados_sem_ocorrencia.append(item)
    return encontrados_sem_ocorrencia, com_ocorrencia


def _linhas_tabela_item(item, txt, txt_center):
    """Monta as linhas da tabela para um item (bem) da conciliação."""
    bem = item.bem
    num = (getattr(bem, "numero_patrimonial", None) or "-").strip()
    val = formatar_moeda_brasileira(
        getattr(bem, "valor_unitario", None) or Decimal("0.00")
    )
    descricao = (getattr(bem, "descricao", None) or "-").strip()
    marca = (getattr(bem, "marca", None) or "-").strip()
    modelo = (getattr(bem, "modelo", None) or "-").strip()
    situacao = item.get_situacao_display()
    linha_topo = [
        Paragraph(f"<b>Nº PATRIMONIAL:</b> {num}", txt),
        Paragraph("", txt),
        Paragraph(f"<b>VALOR:</b> {val}", txt_center),
    ]
    linha_desc = [
        Paragraph(f"<b>DESCRIÇÃO:</b> {descricao}", txt),
        Paragraph(f"<b>MARCA:</b> {marca}", txt),
        Paragraph(f"<b>MODELO:</b> {modelo}", txt),
    ]
    linha_situacao = [
        Paragraph(f"<b>SITUAÇÃO:</b> {situacao}", txt),
        Paragraph("", txt),
        Paragraph("", txt),
    ]
    rows = [linha_topo, linha_desc, linha_situacao]
    oc = item.ocorrencias.first() if item.tem_ocorrencia else None
    if oc:
        registrado_por = obter_rf_usuario(getattr(oc, "registrado_por", None))
        registrado_em = _fmt_date(getattr(oc, "registrado_em", None))
        obs = (getattr(oc, "observacao", "") or "").strip() or "-"
        div = (getattr(oc, "divergencia", "") or "").strip() or "-"
        rows.append(
            [
                Paragraph(f"<b>Observação/Divergência:</b> {obs}", txt),
                Paragraph("", txt),
                Paragraph("", txt),
            ]
        )
        rows.append(
            [
                Paragraph(f"<b>Divergência:</b> {div}", txt),
                Paragraph("", txt),
                Paragraph("", txt),
            ]
        )
        rows.append(
            [
                Paragraph("", txt),
                Paragraph(f"<b>Registrado por:</b> {registrado_por}", txt),
                Paragraph(f"<b>Registrado em:</b> {registrado_em}", txt),
            ]
        )
    return rows, oc


def _tabela_item_conciliacao(rows, oc):
    """Cria a Table (reportlab) com estilo aplicado para um item."""
    box = Table(rows, colWidths=[10.0 * cm, 4.0 * cm, 4.0 * cm])
    style_cmds = [
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("BACKGROUND", (0, 0), (-1, 0), PDFConfig.COR_CINZA_CLARO),
    ]
    if oc:
        style_cmds += [
            ("SPAN", (0, 3), (2, 3)),
            ("SPAN", (0, 4), (2, 4)),
            ("BACKGROUND", (0, 3), (2, 4), PDFConfig.COR_CINZA_ZEBRA),
        ]
    box.setStyle(TableStyle(style_cmds))
    return box


def _render_grupo_itens(titulo, lista, estilos, elements):
    """Adiciona ao elements o título do grupo e as tabelas de cada item."""
    txt = estilos["txt"]
    titulo_grupo = estilos["titulo_grupo"]
    txt_center = estilos["txt_center"]
    if not lista:
        return
    elements.append(Paragraph(f"<b>{titulo}</b> ({len(lista)})", titulo_grupo))
    elements.append(Spacer(1, 0.15 * cm))
    for item in lista:
        rows, oc = _linhas_tabela_item(item, txt, txt_center)
        box = _tabela_item_conciliacao(rows, oc)
        elements.append(KeepTogether([box, Spacer(1, 0.15 * cm)]))
    elements.append(Spacer(1, 0.25 * cm))


def _criar_blocos_itens_conciliacao(conciliacao):
    """
    Gera o corpo em blocos por item, agrupando:
    1) Encontrados sem divergência (sem ocorrência)
    2) Itens com ocorrência (OcorrenciaConciliacao)
    """
    elements = []
    styles = getSampleStyleSheet()
    estilos = _estilos_blocos_itens(styles)
    txt = estilos["txt"]

    itens = (
        conciliacao.itens.select_related("bem")
        .prefetch_related("ocorrencias__registrado_por")
        .all()
        .order_by("bem__numero_patrimonial")
    )
    encontrados_sem_ocorrencia, com_ocorrencia = _classificar_itens_conciliacao(itens)

    _render_grupo_itens(
        "Itens encontrados sem divergência", encontrados_sem_ocorrencia, estilos, elements
    )
    _render_grupo_itens(
        "Itens com ocorrência / divergência", com_ocorrencia, estilos, elements
    )

    if not encontrados_sem_ocorrencia and not com_ocorrencia:
        elements.append(Paragraph("Nenhum item encontrado para esta conciliação.", txt))

    return elements


def gerar_pdf_conciliacao(conciliacao, usuario_gerador=None, data_geracao=None):
    """
    Gera PDF da Conciliação no MESMO padrão do CIMBPM:
    - BaseDocTemplate + Frame + PageTemplate
    - Cabeçalho e rodapé desenhados por página
    - Margens, linhas, fontes e cores idênticas
    """
    buffer = BytesIO()

    data_emissao = timezone.localtime(timezone.now())

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PDFConfig.MARGEM_ESQUERDA,
        rightMargin=PDFConfig.MARGEM_DIREITA,
        topMargin=PDFConfig.MARGEM_SUPERIOR,
        bottomMargin=PDFConfig.MARGEM_INFERIOR,
        title=f"CONCILIAÇÃO {conciliacao.numero_conciliacao}",
        author="Sistema de Bens Físicos - SME",
    )

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")

    def on_page(canvas, doc_):
        canvas.saveState()
        _desenhar_cabecalho_em_pagina(canvas, doc_, conciliacao, data_emissao)
        _desenhar_rodape_em_pagina(
            canvas, doc_, conciliacao, usuario_gerador, data_geracao
        )
        canvas.restoreState()

    template = PageTemplate(id="todas_paginas", frames=[frame], onPage=on_page)
    doc.addPageTemplates([template])

    elements = []
    elements.extend(_criar_informacoes_gerais_conciliacao(conciliacao))
    elements.append(Spacer(1, 0.2 * cm))
    elements.extend(_criar_blocos_itens_conciliacao(conciliacao))
    doc.build(elements, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer
