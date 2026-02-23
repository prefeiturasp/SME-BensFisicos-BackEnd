"""Testes para bem_patrimonial.pdf_utils."""
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone
import pytz

from bem_patrimonial.pdf_utils import (
    PDFConfigBase,
    extrair_codigo_ua,
    formatar_moeda_brasileira,
    obter_nome_usuario,
    criar_estilo_base,
    carregar_logo,
    formatar_data,
    formatar_datahora_geracao,
    criar_info_geracao_paragraph,
)


class TestExtrairCodigoUA(TestCase):
    def test_codigo_com_ponto_usa_ultimo_grupo(self):
        self.assertEqual(extrair_codigo_ua("01.16.10.379"), "379")
        self.assertEqual(extrair_codigo_ua("001.0001"), "001")

    def test_codigo_sem_ponto_usa_ultimos_3_digitos(self):
        self.assertEqual(extrair_codigo_ua("379"), "379")
        self.assertEqual(extrair_codigo_ua("1234"), "234")

    def test_vazio_ou_none_retorna_000(self):
        self.assertEqual(extrair_codigo_ua(""), "000")
        self.assertEqual(extrair_codigo_ua(None), "000")


class TestFormatarMoedaBrasileira(TestCase):
    def test_valor_none_retorna_zero(self):
        self.assertIn("0,00", formatar_moeda_brasileira(None))

    def test_valor_inteiro(self):
        s = formatar_moeda_brasileira(Decimal("1500"))
        self.assertIn("1.500", s)
        self.assertIn("R$", s)

    def test_valor_decimal(self):
        s = formatar_moeda_brasileira(Decimal("99.99"))
        self.assertIn("99,99", s)


class TestObterNomeUsuario(TestCase):
    def test_usuario_none_retorna_traco(self):
        self.assertEqual(obter_nome_usuario(None), "-")

    def test_usuario_com_nome_retorna_nome(self):
        u = MagicMock()
        u.nome = "João"
        u.username = "joao"
        self.assertEqual(obter_nome_usuario(u), "João")

    def test_usuario_sem_nome_retorna_username(self):
        u = MagicMock()
        u.nome = None
        u.username = "joao"
        self.assertEqual(obter_nome_usuario(u), "joao")


class TestCriarEstiloBase(TestCase):
    def test_retorna_paragraph_style(self):
        from reportlab.lib.styles import getSampleStyleSheet

        styles = getSampleStyleSheet()
        estilo = criar_estilo_base("Teste", styles)
        self.assertEqual(estilo.name, "Teste")
        self.assertEqual(estilo.fontSize, PDFConfigBase.FONTE_PADRAO)

    def test_config_none_usa_pdf_config_base(self):
        from reportlab.lib.styles import getSampleStyleSheet

        styles = getSampleStyleSheet()
        estilo = criar_estilo_base("Teste", styles, config_cls=None)
        self.assertEqual(estilo.fontSize, PDFConfigBase.FONTE_PADRAO)


class TestCarregarLogo(TestCase):
    @patch("bem_patrimonial.pdf_utils.settings")
    def test_sem_static_root_retorna_paragraph_fallback(self, mock_settings):
        mock_settings.STATIC_ROOT = None
        mock_settings.STATICFILES_DIRS = None
        from reportlab.lib.styles import getSampleStyleSheet

        styles = getSampleStyleSheet()
        result = carregar_logo(styles)
        self.assertIsNotNone(result)
        from reportlab.platypus import Paragraph

        self.assertIsInstance(result, Paragraph)

    @patch("bem_patrimonial.pdf_utils.os.path.exists", return_value=False)
    @patch("bem_patrimonial.pdf_utils.settings")
    def test_arquivo_nao_existe_retorna_fallback(self, mock_settings, mock_exists):
        mock_settings.STATIC_ROOT = "/tmp/static"
        mock_settings.STATICFILES_DIRS = None
        from reportlab.lib.styles import getSampleStyleSheet

        styles = getSampleStyleSheet()
        result = carregar_logo(styles)
        self.assertIsNotNone(result)


class TestFormatarData(TestCase):
    def test_none_retorna_vazio(self):
        self.assertEqual(formatar_data(None), "")

    def test_data_formatada(self):
        from datetime import date

        self.assertEqual(formatar_data(date(2025, 3, 15)), "15/03/2025")


class TestFormatarDatahoraGeracao(TestCase):
    def test_formato_contem_data_e_hora(self):
        from datetime import datetime

        dt = datetime(2025, 2, 10, 14, 30)
        result = formatar_datahora_geracao(dt)
        self.assertIn("10/02/2025", result)
        self.assertIn("às", result)

    @patch("bem_patrimonial.pdf_utils.timezone.now")
    def test_none_usa_timezone_now(self, mock_now):
        from datetime import datetime

        mock_now.return_value = datetime(2025, 1, 5, 12, 0)
        result = formatar_datahora_geracao(None)
        self.assertIn("05/01/2025", result)


class TestCriarInfoGeracaoParagraph(TestCase):
    def test_retorna_lista_com_paragraph(self):
        from reportlab.platypus import Paragraph, Spacer

        u = MagicMock()
        u.nome = "Test"
        u.username = "test"
        elements = criar_info_geracao_paragraph(usuario=u)
        self.assertEqual(len(elements), 2)
        self.assertIsInstance(elements[0], Spacer)
        self.assertIsInstance(elements[1], Paragraph)
        self.assertIn("Test", elements[1].text)
        self.assertIn("Gerado por", elements[1].text)

    def test_usuario_none_mostra_traco(self):
        elements = criar_info_geracao_paragraph(usuario=None)
        self.assertIn("-", elements[1].text)
