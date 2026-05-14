from io import BytesIO

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import IntegerField, Max
from django.db.models.functions import Cast, Substr
from django.utils import timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Spacer, Paragraph, Table

from bem_patrimonial.models import TransferenciaBemPatrimonial
from bem_patrimonial.pdf_utils import (
    PDFConfigBase as PDFConfig,
    criar_estilo_base,
    extrair_codigo_ua,
    formatar_data,
    obter_rf_usuario,
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


def obter_bens_transferencia(transferencia):
    itens = transferencia.itens.select_related("bem").all()
    bens = [item.bem for item in itens]
    return sorted(bens, key=lambda b: b.numero_patrimonial or "")


def gerar_numero_ntbpm(transferencia):
    if not isinstance(transferencia, TransferenciaBemPatrimonial):
        raise ValidationError("Objeto inválido para geração de NTBPM.")

    ano_transferencia = (
        transferencia.efetivado_em.year
        if transferencia.efetivado_em
        else timezone.localdate().year
    )
    codigo_origem = extrair_codigo_ua(transferencia.unidade_orcamentaria_origem.codigo)
    codigo_destino = extrair_codigo_ua(transferencia.unidade_orcamentaria_destino.codigo)

    with transaction.atomic():
        ultimo_sequencial = (
            TransferenciaBemPatrimonial.objects.select_for_update()
            .filter(
                numero_ntbpm__endswith=f".{ano_transferencia}",
                numero_ntbpm__isnull=False,
            )
            .exclude(numero_ntbpm__exact="")
            .annotate(sequencial_str=Substr("numero_ntbpm", 9, 7))
            .aggregate(max_seq=Max(Cast("sequencial_str", IntegerField())))
        )["max_seq"]

        numero_sequencial = (ultimo_sequencial or 0) + 1

    return f"{codigo_origem}.{codigo_destino}.{numero_sequencial:07d}.{ano_transferencia}"


def gerar_pdf_ntbpm(transferencia, usuario_gerador=None, data_geracao=None):
    if not isinstance(transferencia, TransferenciaBemPatrimonial):
        raise ValidationError("Objeto inválido para gerar NTBPM.")

    if not transferencia.efetivado_em:
        raise ValidationError("Só é possível gerar NTBPM para transferências efetivadas.")

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
        valor_data_2=formatar_data(transferencia.efetivado_em),
        valor_numero=transferencia.numero_ntbpm or "",
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
    ua_destino = transferencia.unidade_administrativa_destino

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
            uo_origem.nome,
            "UNIDADE ORÇAMENTÁRIA DE ORIGEM",
            getattr(uo_origem, "sigla", "-"),
            getattr(uo_origem, "nome", "-"),
            getattr(uo_origem, "codigo", "-"),
            label_style,
            value_style,
        )
    )

    info_data.extend(
        _criar_linha_ua(
            ua_destino.unidade_orcamentaria.nome,
            "UNIDADE ORÇAMENTÁRIA / UNIDADE ADMINISTRATIVA DE DESTINO",
            getattr(ua_destino, "sigla", "-"),
            getattr(ua_destino, "nome", "-"),
            getattr(ua_destino, "codigo", "-"),
            label_style,
            value_style,
        )
    )

    info_data.extend(
        [
            [
                Paragraph("<b>NÚMERO DO PROCESSO</b>", label_style),
                Paragraph("<b>DATA DA TRANSFERÊNCIA</b>", label_style),
                Paragraph("<b>STATUS</b>", label_style),
            ],
            [
                Paragraph(str(transferencia.numero_processo or "-").upper(), value_style),
                Paragraph(
                    transferencia.efetivado_em.strftime(DATE_FMT_BR)
                    if transferencia.efetivado_em
                    else "-",
                    value_style,
                ),
                Paragraph("TRANSFERIDO", value_style),
            ],
        ]
    )

    info_table = Table(info_data, colWidths=[5.0 * cm, 10.0 * cm, 3.0 * cm])
    aplicar_estilo_tabela_info(info_table, linhas_cabecalho=[0, 2, 4], config_cls=PDFConfig)

    return [info_table]


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


def _criar_rodape_ntbpm(transferencia):
    responsavel_transferencia = obter_rf_usuario(getattr(transferencia, "criado_por", None))
    unidade_destino = str(getattr(transferencia, "unidade_administrativa_destino", "-"))

    return criar_tabela_rodape_responsaveis(
        label_esquerda="RESPONSÁVEL DA UNIDADE ORÇAMENTÁRIA QUE TRANSFERE",
        label_direita="RESPONSÁVEL DA UNIDADE ORÇAMENTÁRIA QUE RECEBE",
        valor_esquerda=responsavel_transferencia,
        valor_direita=unidade_destino,
        config_cls=PDFConfig,
    )