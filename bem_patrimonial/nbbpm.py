from io import BytesIO

from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.utils import timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import Table, Paragraph, Spacer, BaseDocTemplate, Frame, PageTemplate

from bem_patrimonial import constants
from bem_patrimonial.models import BaixaFisicaBemPatrimonial
from bem_patrimonial.pdf_utils import (
    PDFConfigBase as PDFConfig,
    criar_estilo_base,
    obter_rf_usuario,
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

DATE_FMT_BR = "%d/%m/%Y"


def obter_bens_baixa(baixa):
    itens = baixa.itens.select_related("bem").all()
    bens = [item.bem for item in itens]
    return sorted(bens, key=lambda b: b.numero_patrimonial or "")


def gerar_numero_nbbpm(baixa):
    """Compatibilidade: delega ao serviço unificado (prefixo fixo 001, sequencial global por ano)."""
    if not isinstance(baixa, BaixaFisicaBemPatrimonial):
        raise ValidationError("Objeto inválido para geração de NBBPM.")

    if getattr(baixa, "data_aprovacao", None):
        try:
            ano_baixa = baixa.data_aprovacao.year
        except Exception:
            ano_baixa = timezone.localdate().year
    elif getattr(baixa, "data_baixa", None):
        try:
            ano_baixa = baixa.data_baixa.year
        except Exception:
            ano_baixa = timezone.localdate().year
    else:
        ano_baixa = timezone.localdate().year

    from bem_patrimonial.services.nbbpm_numero import gerar_numero_para_ano

    return gerar_numero_para_ano(ano_baixa)


def gerar_pdf_nbbpm(baixa, usuario_gerador=None, data_geracao=None):
    if not isinstance(baixa, BaixaFisicaBemPatrimonial):
        raise ValidationError("Objeto inválido para gerar NBBPM.")

    if baixa.status != constants.ACEITA:
        raise ValidationError("Só é possível gerar NBBPM para Baixas Físicas aprovadas (ACEITA).")

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
        _desenhar_rodape_em_pagina(
            canvas,
            doc_,
            baixa,
            usuario_gerador=usuario_gerador,
            data_geracao=data_geracao,
        )
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
    cabecalho = _criar_cabecalho_e_registro_nbbpm(baixa)
    if cabecalho:
        desenhar_tabela_no_canvas(canvas, doc, cabecalho[0], A4[1] - 1.0 * cm)


def _desenhar_rodape_em_pagina(canvas, doc, baixa, usuario_gerador=None, data_geracao=None):
    tabela_rodape = _criar_rodape_nbbpm(baixa)
    usuario = usuario_gerador or getattr(baixa, "criado_por", None)

    desenhar_rodape_padrao(
        canvas,
        doc,
        tabela_rodape[0] if tabela_rodape else None,
        usuario=usuario,
        data_geracao=data_geracao,
        config_cls=PDFConfig,
    )


def _criar_cabecalho_e_registro_nbbpm(baixa):
    return criar_cabecalho_registro_documento(
        titulo_documento="NOTA DE BAIXA DE BENS PATRIMONIAIS MÓVEIS E INTANGÍVEIS (NBBPM)",
        titulo_registro="REGISTRO DA NBBPM",
        label_data_1="BAIXA",
        label_data_2="APROVAÇÃO",
        label_numero="NÚMERO NBBPM",
        valor_data_1=formatar_data(baixa.data_baixa),
        valor_data_2=formatar_data(baixa.data_aprovacao),
        valor_numero=baixa.numero_nbbpm or "",
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


def _criar_informacoes_gerais(baixa):
    styles = getSampleStyleSheet()

    label_style = criar_estilo_base(
        "InfoLabel",
        styles,
        config_cls=PDFConfig,
        fontName="Helvetica-Bold",
        alignment=TA_LEFT,
    )
    value_style = criar_estilo_base("InfoValue", styles, config_cls=PDFConfig, alignment=TA_LEFT)

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
                    baixa.data_baixa.strftime(DATE_FMT_BR) if baixa.data_baixa else "-",
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
    aplicar_estilo_tabela_info(info_table, linhas_cabecalho=[0, 2, 4], config_cls=PDFConfig)

    return [info_table]


def _criar_tabela_bens(baixa):
    bens = obter_bens_baixa(baixa)
    return criar_tabela_bens_padrao(
        bens=bens,
        descricao_fn=lambda bem: str((getattr(bem, "descricao", None) or getattr(bem, "nome", None) or "-")).upper(),
        config_cls=PDFConfig,
    )


def _criar_total_bens(baixa):
    bens = obter_bens_baixa(baixa)
    return criar_tabela_total_bens(bens=bens, config_cls=PDFConfig)


def _criar_rodape_nbbpm(baixa):
    resp_baixa = getattr(baixa, "criado_por", None)
    responsavel_baixa = obter_rf_usuario(resp_baixa)

    resp_aprov = getattr(baixa, "aprovado_por", None)
    if resp_aprov:
        responsavel_aprov = obter_rf_usuario(resp_aprov)
    else:
        responsavel_aprov = ""

    return criar_tabela_rodape_responsaveis(
        label_esquerda="RESPONSÁVEL PELA BAIXA",
        label_direita="RESPONSÁVEL PELA APROVAÇÃO",
        valor_esquerda=responsavel_baixa,
        valor_direita=responsavel_aprov,
        config_cls=PDFConfig,
    )


def http_response_nbbpm(baixa, usuario_gerador=None):
    buffer = gerar_pdf_nbbpm(baixa, usuario_gerador=usuario_gerador)
    filename = f"NBBPM_{baixa.numero_nbbpm}.pdf"

    resp = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
