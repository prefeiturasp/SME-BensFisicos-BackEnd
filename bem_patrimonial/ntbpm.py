from io import BytesIO

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import IntegerField, Max, Value
from django.db.models.functions import Cast, Replace, Substr
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Spacer,
    Paragraph,
    Table,
    TableStyle,
)

from bem_patrimonial.models import TransferenciaBemPatrimonial
from bem_patrimonial.pdf_utils import (
    PDFConfigBase as PDFConfig,
    criar_estilo_base,
    extrair_codigo_ua,
    formatar_data,
)
from bem_patrimonial.documentos_pdf_utils import (
    aplicar_estilo_tabela_info,
    criar_cabecalho_registro_documento,
    criar_tabela_bens_padrao,
    criar_tabela_rodape_responsaveis,
    criar_tabela_total_bens,
    desenhar_rodape_padrao,
    desenhar_tabela_no_canvas,
)

DATE_FMT_BR = "%d/%m/%Y"


def obter_bens_transferencia(transferencia):
    itens = transferencia.itens.select_related("bem").all()
    bens = [item.bem for item in itens]
    return sorted(bens, key=lambda b: b.numero_patrimonial or "")


def gerar_numero_ntbpm(transferencia):
    if not isinstance(transferencia, TransferenciaBemPatrimonial):
        raise ValidationError("Objeto inválido para geração de NTBPM.")

    """
    Modelo alinhado ao NBBPM: <COD_UA_DESTINO>.<SEQ_7>.<ANO>
    Ex: 001.0000001.2026
    """

    ano_transferencia = (
        transferencia.criado_em.year
        if transferencia.criado_em
        else timezone.localdate().year
    )
    codigo_ua_destino = extrair_codigo_ua(
        getattr(transferencia.unidade_administrativa_destino, "codigo", "")
    )

    with transaction.atomic():
        qs = (
            TransferenciaBemPatrimonial.objects.select_for_update()
            .filter(
                numero_ntbpm__endswith=f".{ano_transferencia}",
                numero_ntbpm__isnull=False,
            )
            .exclude(numero_ntbpm__exact="")
        )

        sequencial_raw = Substr("numero_ntbpm", 5, 7)
        sequencial_digits = Replace(sequencial_raw, Value("."), Value(""))

        ultimo_sequencial = qs.annotate(
            sequencial_int=Cast(sequencial_digits, IntegerField())
        ).aggregate(max_seq=Max("sequencial_int"))["max_seq"]

        numero_sequencial = (ultimo_sequencial or 0) + 1

    return f"{codigo_ua_destino}.{numero_sequencial:07d}.{ano_transferencia}"


def gerar_pdf_ntbpm(transferencia, usuario_gerador=None, data_geracao=None):
    if not isinstance(transferencia, TransferenciaBemPatrimonial):
        raise ValidationError("Objeto inválido para gerar NTBPM.")

    if not getattr(transferencia, "numero_ntbpm", None):
        transferencia.numero_ntbpm = gerar_numero_ntbpm(transferencia)
        transferencia.save(update_fields=["numero_ntbpm"])

    buffer = BytesIO()

    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=PDFConfig.MARGEM_ESQUERDA,
        rightMargin=PDFConfig.MARGEM_DIREITA,
        topMargin=PDFConfig.MARGEM_SUPERIOR,
        bottomMargin=PDFConfig.MARGEM_INFERIOR,
        title=f"NTBPM {transferencia.numero_ntbpm}",
        author="Sistema de Bens Físicos - SME",
    )

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")

    def on_page(canvas, doc_):
        canvas.saveState()
        _desenhar_cabecalho_em_pagina(canvas, doc_, transferencia)
        _desenhar_rodape_em_pagina(
            canvas,
            doc_,
            transferencia,
            usuario_gerador=usuario_gerador,
            data_geracao=data_geracao,
        )
        canvas.restoreState()

    template = PageTemplate(id="todas_paginas", frames=[frame], onPage=on_page)
    doc.addPageTemplates([template])

    elements = []
    elements.extend(_criar_informacoes_gerais(transferencia))
    elements.append(Spacer(1, 0.2 * cm))
    elements.extend(_criar_tabela_bens(transferencia))
    elements.append(Spacer(1, 0.1 * cm))
    elements.extend(_criar_total_bens(transferencia))
    elements.append(Spacer(1, 0.2 * cm))
    elements.extend(_criar_informacoes_complementares(transferencia))

    doc.build(elements)
    buffer.seek(0)
    return buffer


def _desenhar_cabecalho_em_pagina(canvas, doc, transferencia):
    cabecalho = _criar_cabecalho_e_registro_ntbpm(transferencia)
    if cabecalho:
        desenhar_tabela_no_canvas(canvas, doc, cabecalho[0], A4[1] - 1.0 * cm)


def _desenhar_rodape_em_pagina(
    canvas,
    doc,
    transferencia,
    usuario_gerador=None,
    data_geracao=None,
):
    tabela_rodape = _criar_rodape_ntbpm(transferencia)
    usuario = usuario_gerador or getattr(transferencia, "criado_por", None)

    desenhar_rodape_padrao(
        canvas,
        doc,
        tabela_rodape[0] if tabela_rodape else None,
        usuario=usuario,
        data_geracao=data_geracao,
        config_cls=PDFConfig,
    )


def _criar_cabecalho_e_registro_ntbpm(transferencia):
    return criar_cabecalho_registro_documento(
        titulo_documento="NOTA DE TRANSFERÊNCIA DE BENS PATRIMONIAIS MÓVEIS E INTANGÍVEIS - NTBPM",
        titulo_registro="REGISTRO DA NTBPM",
        label_data_1="EMISSÃO",
        label_data_2="ACEITE",
        label_numero="NÚMERO NTBPM",
        valor_data_1=formatar_data(transferencia.criado_em),
        valor_data_2=formatar_data(transferencia.criado_em),
        valor_numero=transferencia.numero_ntbpm or "",
        config_cls=PDFConfig,
    )


def _criar_linha_uo(label, sigla, nome, codigo, label_style, value_style):
    return [
        [
            Paragraph("<b>PREFIXO</b>", label_style),
            Paragraph(f"<b>{label}</b>", label_style),
            Paragraph("<b>CÓDIGO</b>", label_style),
        ],
        [
            Paragraph(str(sigla or "-").upper(), value_style),
            Paragraph(str(nome or "-").upper(), value_style),
            Paragraph(str(codigo or "-"), value_style),
        ],
    ]


def _criar_linha_orgao(sigla_orgao, orgao, codigo_orgao, label_style, value_style):
    return [
        [
            Paragraph("<b>PREFIXO</b>", label_style),
            Paragraph("<b>ÓRGÃO</b>", label_style),
            Paragraph("<b>CÓDIGO</b>", label_style),
        ],
        [
            Paragraph(str(sigla_orgao or "-").upper(), value_style),
            Paragraph(str(orgao or "-").upper(), value_style),
            Paragraph(str(codigo_orgao or "-"), value_style),
        ],
    ]


def _criar_tabela_resumo_transferencia(transferencia, label_style, value_style):
    resumo_table = Table(
        [
            [
                Paragraph("<b>NÚMERO DO PROCESSO</b>", label_style),
                Paragraph("<b>DATA DA TRANSFERÊNCIA</b>", label_style),
                Paragraph("<b>STATUS</b>", label_style),
            ],
            [
                Paragraph(
                    str(transferencia.numero_processo or "-").upper(),
                    value_style,
                ),
                Paragraph(
                    transferencia.criado_em.strftime(DATE_FMT_BR)
                    if transferencia.criado_em
                    else "-",
                    value_style,
                ),
                Paragraph("TRANSFERIDO", value_style),
            ],
        ],
        colWidths=[8 * cm, 5 * cm, 5 * cm],
    )
    resumo_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (2, 0), PDFConfig.COR_CINZA_CLARO),
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
    return resumo_table


def _criar_tabela_observacao(transferencia, label_style, value_style):
    observacao_table = Table(
        [
            [Paragraph("<b>OBSERVAÇÃO</b>", label_style)],
            [Paragraph(str(transferencia.observacao or "-"), value_style)],
        ],
        colWidths=[18 * cm],
    )
    observacao_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), PDFConfig.COR_CINZA_CLARO),
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
    return observacao_table


def _criar_informacoes_gerais(transferencia):
    styles = getSampleStyleSheet()

    label_style = criar_estilo_base(
        "InfoLabelNTBPM",
        styles,
        config_cls=PDFConfig,
        fontName="Helvetica-Bold",
        alignment=TA_LEFT,
    )
    value_style = criar_estilo_base(
        "InfoValueNTBPM",
        styles,
        config_cls=PDFConfig,
        alignment=TA_LEFT,
    )

    uo_origem = transferencia.unidade_orcamentaria_origem
    uo_destino = transferencia.unidade_orcamentaria_destino

    info_data = []
    info_data.extend(
        _criar_linha_orgao(
            getattr(uo_origem, "sigla_orgao", "-"),
            getattr(uo_origem, "orgao", "-"),
            getattr(uo_origem, "codigo_orgao", "-"),
            label_style,
            value_style,
        )
    )
    info_data.extend(
        _criar_linha_uo(
            "UNIDADE ORÇAMENTÁRIA QUE TRANSFERE",
            getattr(uo_origem, "sigla", "-"),
            getattr(uo_origem, "nome", "-"),
            getattr(uo_origem, "codigo", "-"),
            label_style,
            value_style,
        )
    )
    info_data.extend(
        _criar_linha_orgao(
            getattr(uo_destino, "sigla_orgao", "-"),
            getattr(uo_destino, "orgao", "-"),
            getattr(uo_destino, "codigo_orgao", "-"),
            label_style,
            value_style,
        )
    )
    info_data.extend(
        _criar_linha_uo(
            "UNIDADE ORÇAMENTÁRIA QUE RECEBE",
            getattr(uo_destino, "sigla", "-"),
            getattr(uo_destino, "nome", "-"),
            getattr(uo_destino, "codigo", "-"),
            label_style,
            value_style,
        )
    )

    info_table = Table(info_data, colWidths=[4.0 * cm, 10.5 * cm, 3.5 * cm])
    aplicar_estilo_tabela_info(
        info_table,
        linhas_cabecalho=[0, 2, 4, 6],
        config_cls=PDFConfig,
    )

    return [
        info_table,
        Spacer(1, 0.1 * cm),
        _criar_tabela_resumo_transferencia(transferencia, label_style, value_style),
    ]


def _criar_tabela_bens(transferencia):
    bens = obter_bens_transferencia(transferencia)
    return criar_tabela_bens_padrao(
        bens=bens,
        descricao_fn=lambda bem: str(getattr(bem, "descricao", "-") or "-").upper(),
        config_cls=PDFConfig,
    )


def _criar_total_bens(transferencia):
    bens = obter_bens_transferencia(transferencia)
    return criar_tabela_total_bens(bens=bens, config_cls=PDFConfig)


def _criar_informacoes_complementares(transferencia):
    styles = getSampleStyleSheet()
    label_style = criar_estilo_base(
        "ComplementoLabelNTBPM",
        styles,
        config_cls=PDFConfig,
        fontName="Helvetica-Bold",
        alignment=TA_LEFT,
    )
    value_style = criar_estilo_base(
        "ComplementoValueNTBPM",
        styles,
        config_cls=PDFConfig,
        alignment=TA_LEFT,
    )

    return [
        _criar_tabela_observacao(
            transferencia,
            label_style,
            value_style,
        )
    ]


def _criar_rodape_ntbpm():
    return criar_tabela_rodape_responsaveis(
        label_esquerda="RESPONSÁVEL DA UNIDADE ORÇAMENTÁRIA QUE TRANSFERE",
        label_direita="RESPONSÁVEL DA UNIDADE ORÇAMENTÁRIA QUE RECEBE",
        valor_esquerda="",
        valor_direita="",
        config_cls=PDFConfig,
    )