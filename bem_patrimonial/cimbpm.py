from io import BytesIO

from django.db import transaction
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (
    Table,
    Paragraph,
    Spacer,
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Image as ReportLabImage,
)

from bem_patrimonial.pdf_utils import (
    PDFConfigBase as PDFConfig,
    extrair_codigo_ua,
    criar_estilo_base,
    formatar_moeda_brasileira,
    obter_nome_usuario,
    formatar_data,
)
from bem_patrimonial.documentos_pdf_utils import (
    aplicar_estilo_tabela_info,
    criar_cabecalho_registro_documento,
    criar_linha_ua_info,
    criar_tabela_bens_padrao,
    criar_tabela_rodape_responsaveis,
    criar_tabela_total_bens,
    desenhar_rodape_padrao,
    desenhar_tabela_no_canvas,
)

Image = ReportLabImage


def obter_bens_movimentacao(movimentacao):
    bens_itens = movimentacao.itens.select_related("bem").all()
    bens = [item.bem for item in bens_itens]

    # Fallback para compatibilidade com modelo antigo
    if not bens and movimentacao.bem_patrimonial:
        bens = [movimentacao.bem_patrimonial]

    return sorted(bens, key=lambda b: b.numero_patrimonial or "")


def gerar_numero_cimbpm(movimentacao):
    from django.db.models import IntegerField, Max
    from django.db.models.functions import Cast, Substr

    from bem_patrimonial.models import MovimentacaoBemPatrimonial

    ano_movimentacao = movimentacao.criado_em.year
    codigo_origem = extrair_codigo_ua(movimentacao.unidade_administrativa_origem.codigo)
    codigo_destino = extrair_codigo_ua(movimentacao.unidade_administrativa_destino.codigo)

    with transaction.atomic():
        ultimo_sequencial = (
            MovimentacaoBemPatrimonial.objects.select_for_update()
            .filter(
                numero_cimbpm__endswith=f".{ano_movimentacao}",
                numero_cimbpm__isnull=False,
            )
            .annotate(sequencial_str=Substr("numero_cimbpm", 9, 7))
            .aggregate(max_seq=Max(Cast("sequencial_str", IntegerField())))
        )["max_seq"]

        numero_sequencial = (ultimo_sequencial or 0) + 1

    return f"{codigo_origem}.{codigo_destino}.{numero_sequencial:07d}.{ano_movimentacao}"


def gerar_pdf_cimbpm(movimentacao, data_aceite=None, usuario_gerador=None, data_geracao=None):
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

    def on_page(canvas, doc_):
        canvas.saveState()
        _desenhar_cabecalho_em_pagina(canvas, doc_, movimentacao, data_aceite)
        _desenhar_rodape_em_pagina(
            canvas,
            doc_,
            movimentacao,
            data_aceite,
            usuario_gerador=usuario_gerador,
            data_geracao=data_geracao,
        )
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
    cabecalho = _criar_cabecalho_e_registro_cimbpm(movimentacao, data_aceite)
    if cabecalho:
        desenhar_tabela_no_canvas(canvas, doc, cabecalho[0], A4[1] - 1.0 * cm)


def _desenhar_rodape_em_pagina(
    canvas,
    doc,
    movimentacao,
    data_aceite,
    usuario_gerador=None,
    data_geracao=None,
):
    tabela_rodape = _criar_rodape_cimbpm(movimentacao, data_aceite)
    usuario = usuario_gerador or getattr(movimentacao, "solicitado_por", None)

    desenhar_rodape_padrao(
        canvas,
        doc,
        tabela_rodape[0] if tabela_rodape else None,
        usuario=usuario,
        data_geracao=data_geracao,
        config_cls=PDFConfig,
    )


def _criar_cabecalho_e_registro_cimbpm(movimentacao, data_aceite):
    return criar_cabecalho_registro_documento(
        titulo_documento="CONTROLE INTERNO DA MOVIMENTAÇÃO DE BENS PATRIMONIAIS MÓVEIS E INTANGÍVEIS (CIMBPM)",
        titulo_registro="REGISTRO DA CIMBPM",
        label_data_1="EMISSÃO",
        label_data_2="ACEITE",
        label_numero="NÚMERO CIMBPM",
        valor_data_1=formatar_data(movimentacao.criado_em),
        valor_data_2=formatar_data(data_aceite),
        valor_numero=movimentacao.numero_cimbpm or "",
        config_cls=PDFConfig,
    )


def _criar_linha_ua(unidade_orcamentaria, label, sigla, nome, codigo, label_style, value_style):
    return criar_linha_ua_info(
        unidade_orcamentaria=unidade_orcamentaria,
        label=label,
        sigla=sigla,
        nome=nome,
        codigo=codigo,
        label_style=label_style,
        value_style=value_style,
    )


def _criar_informacoes_gerais(movimentacao):
    styles = getSampleStyleSheet()

    label_style = criar_estilo_base(
        "InfoLabel",
        styles,
        config_cls=PDFConfig,
        fontName="Helvetica-Bold",
        alignment=TA_LEFT,
    )
    value_style = criar_estilo_base("InfoValue", styles, config_cls=PDFConfig, alignment=TA_LEFT)

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
            ua_origem.unidade_orcamentaria.nome,
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
            ua_destino.unidade_orcamentaria.nome,
            "UNIDADE ORÇAMENTÁRIA / UNIDADE ADMINISTRATIVA QUE RECEBE",
            ua_destino.sigla,
            ua_destino.nome,
            ua_destino.codigo,
            label_style,
            value_style,
        )
    )

    info_table = Table(info_data, colWidths=[2.5 * cm, 12.5 * cm, 3 * cm])
    aplicar_estilo_tabela_info(info_table, linhas_cabecalho=[0, 2, 4], config_cls=PDFConfig)

    return [info_table]


def _criar_tabela_bens(movimentacao):
    bens = obter_bens_movimentacao(movimentacao)
    return criar_tabela_bens_padrao(
        bens=bens,
        descricao_fn=lambda bem: str(getattr(bem, "descricao", "-") or "-").upper(),
        config_cls=PDFConfig,
    )


def _criar_total_bens(movimentacao):
    bens = obter_bens_movimentacao(movimentacao)
    return criar_tabela_total_bens(bens=bens, config_cls=PDFConfig)


def _criar_rodape_cimbpm(movimentacao, data_aceite):
    responsavel_entrega_obj = movimentacao.solicitado_por
    nome_entrega = obter_nome_usuario(responsavel_entrega_obj).upper()
    rf_entrega = (
        responsavel_entrega_obj.rf if responsavel_entrega_obj.rf else "-"
    )
    responsavel_entrega = f"{nome_entrega} - RF: {rf_entrega}"

    responsavel_recebimento = ""
    if data_aceite and movimentacao.aprovado_por:
        responsavel_rec = movimentacao.aprovado_por
        nome_recebimento = obter_nome_usuario(responsavel_rec).upper()
        rf_recebimento = responsavel_rec.rf if responsavel_rec.rf else "-"
        responsavel_recebimento = f"{nome_recebimento} - RF: {rf_recebimento}"

    return criar_tabela_rodape_responsaveis(
        label_esquerda="RESPONSÁVEL PELA ENTREGA",
        label_direita="RESPONSÁVEL PELO RECEBIMENTO",
        valor_esquerda=responsavel_entrega,
        valor_direita=responsavel_recebimento,
        config_cls=PDFConfig,
    )
