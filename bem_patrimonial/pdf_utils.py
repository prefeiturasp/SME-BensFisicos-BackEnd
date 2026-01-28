import os
import re
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import Image, Paragraph, Spacer

import pytz


class PDFConfigBase:

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

    TZ_PADRAO = "America/Sao_Paulo"

    LOGO_RELATIVE_PATH = os.path.join("img", "prefeitura_default_logo.png")


def extrair_codigo_ua(codigo_completo):
    apenas_numeros = re.sub(r"\D", "", str(codigo_completo or ""))

    if not apenas_numeros:
        return "000"

    if "." in str(codigo_completo):
        ultimo_grupo = str(codigo_completo).split(".")[-1]
        ultimo_numero = re.sub(r"\D", "", ultimo_grupo).lstrip("0") or "0"
    else:
        ultimo_numero = apenas_numeros.lstrip("0") or "0"

    return ultimo_numero.zfill(3)[-3:]


def formatar_moeda_brasileira(valor):
    if valor is None:
        valor = Decimal("0.00")
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def obter_nome_usuario(usuario):
    if not usuario:
        return "-"
    return usuario.nome if getattr(usuario, "nome", None) else usuario.username


def criar_estilo_base(nome, parent_styles, config_cls=PDFConfigBase, **kwargs):
    if config_cls is None:
        config_cls = PDFConfigBase

    defaults = {
        "parent": parent_styles["Normal"],
        "fontSize": config_cls.FONTE_PADRAO,
        "leading": 9,
    }
    defaults.update(kwargs)
    return ParagraphStyle(nome, **defaults)


def carregar_logo(styles, config_cls=PDFConfigBase, width_cm=2.0, height_cm=1.3):
    static_root = settings.STATIC_ROOT or (
        settings.STATICFILES_DIRS[0]
        if getattr(settings, "STATICFILES_DIRS", None)
        else None
    )

    if static_root:
        logo_path = os.path.join(static_root, config_cls.LOGO_RELATIVE_PATH)
        if os.path.exists(logo_path):
            try:
                return Image(logo_path, width=width_cm * cm, height=height_cm * cm)
            except Exception:
                pass

    fallback_style = criar_estilo_base(
        "LogoFallback",
        styles,
        config_cls=config_cls,
        fontSize=9,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )
    return Paragraph("<b>PMSP</b>", fallback_style)


def formatar_data(dt):
    return dt.strftime("%d/%m/%Y") if dt else ""


def formatar_datahora_geracao(data_geracao=None, config_cls=PDFConfigBase):
    tz = pytz.timezone(config_cls.TZ_PADRAO)
    data_ref = data_geracao if data_geracao else timezone.now()

    if timezone.is_naive(data_ref):
        data_ref = timezone.make_aware(data_ref)

    return data_ref.astimezone(tz).strftime("%d/%m/%Y às %H:%M")


def criar_info_geracao_paragraph(
    *, usuario, data_geracao=None, config_cls=PDFConfigBase
):
    styles = getSampleStyleSheet()
    info_style = criar_estilo_base(
        "InfoGeracao",
        styles,
        config_cls=config_cls,
        textColor=colors.grey,
    )

    nome = obter_nome_usuario(usuario)
    quando = formatar_datahora_geracao(data_geracao, config_cls=config_cls)

    return [
        Spacer(1, 0.2 * cm),
        Paragraph(f"Gerado por {nome} em {quando}", info_style),
    ]
