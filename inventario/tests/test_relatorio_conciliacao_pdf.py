"""Testes para inventario.relatorio_conciliacao_pdf."""
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import TestCase

from inventario.relatorio_conciliacao_pdf import (
    formatar_status_para_header,
    formatar_moeda_brasileira,
    obter_nome_usuario,
    _quebrar_texto_longo,
    _fmt_date,
    gerar_pdf_conciliacao,
)
from inventario import constants
from inventario.models import ConciliacaoUA
from dados_comuns.tests.factories import criar_ua
from usuario.models import Usuario


def _conciliacao_mock(status_display="Em aberto", tipo_display="Anual"):
    c = MagicMock()
    c.get_status_display.return_value = status_display
    c.get_tipo_display.return_value = tipo_display
    return c


class TestFormatarStatusParaHeader(TestCase):
    def test_nao_conciliado_retorna_nao_conciliado(self):
        c = _conciliacao_mock(status_display="Fechado pelo Administrador - Não Conciliado")
        self.assertEqual(formatar_status_para_header(c), "Não Conciliado")

    def test_outro_status_retorna_display(self):
        c = _conciliacao_mock(status_display="Aberta")
        self.assertEqual(formatar_status_para_header(c), "Aberta")


class TestFormatarMoedaBrasileiraRelatorio(TestCase):
    def test_none_retorna_zero(self):
        s = formatar_moeda_brasileira(None)
        self.assertIn("0,00", s)

    def test_valor_formatado(self):
        s = formatar_moeda_brasileira(Decimal("1500.50"))
        self.assertIn("R$", s)
        self.assertIn("1.500,50", s)


class TestObterNomeUsuarioRelatorio(TestCase):
    def test_none_retorna_traco(self):
        self.assertEqual(obter_nome_usuario(None), "-")

    def test_com_nome_retorna_nome(self):
        u = MagicMock()
        u.nome = "Maria"
        u.username = "maria"
        self.assertEqual(obter_nome_usuario(u), "Maria")

    def test_sem_nome_retorna_username(self):
        u = MagicMock()
        u.nome = None
        u.username = "maria"
        self.assertEqual(obter_nome_usuario(u), "maria")


class TestQuebrarTextoLongo(TestCase):
    def test_vazio_retorna_traco(self):
        self.assertEqual(_quebrar_texto_longo(""), "-")
        self.assertEqual(_quebrar_texto_longo(None), "-")

    def test_curto_retorna_igual(self):
        self.assertEqual(_quebrar_texto_longo("Curto"), "Curto")

    def test_longo_trunca_com_reticencias(self):
        txt = "a" * 200
        result = _quebrar_texto_longo(txt, max_chars=180)
        self.assertEqual(len(result), 183)
        self.assertTrue(result.endswith("..."))


class TestFmtDate(TestCase):
    def test_none_retorna_traco(self):
        self.assertEqual(_fmt_date(None), "-")

    def test_data_strftime(self):
        from datetime import date

        self.assertEqual(_fmt_date(date(2025, 2, 10)), "10/02/2025")


class TestGerarPdfConciliacao(TestCase):
    """Testes para gerar_pdf_conciliacao (retorno e estrutura)."""

    def setUp(self):
        self.ua = criar_ua(codigo="001.0001", sigla="UA", nome="Unidade")
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.ua.unidade_orcamentaria,
        )
        self.conciliacao = ConciliacaoUA.objects.create(
            numero_conciliacao="001.0001/2025",
            tipo=constants.CONCILIACAO_ANUAL,
            periodo_final=__import__("datetime").date(2025, 12, 31),
            unidade_administrativa=self.ua,
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.user,
        )

    def test_retorna_buffer_bytes(self):
        """gerar_pdf_conciliacao retorna buffer com conteúdo PDF."""
        buffer = gerar_pdf_conciliacao(
            self.conciliacao,
            usuario_gerador=self.user,
        )
        self.assertIsInstance(buffer, BytesIO)
        buffer.seek(0)
        data = buffer.read(100)
        self.assertTrue(data.startswith(b"%PDF"), "Deve iniciar com cabeçalho PDF")
