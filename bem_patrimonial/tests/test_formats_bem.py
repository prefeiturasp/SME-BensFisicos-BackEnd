"""Testes para bem_patrimonial.formats (PDFFormat)."""
from io import BytesIO
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from bem_patrimonial.formats import PDFFormat
from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario


class TestPDFFormat(TestCase):
    """Testes para PDFFormat (exportação de bens em PDF)."""

    def setUp(self):
        self.uo = criar_uo(codigo="701")
        self.ua = criar_ua(uo=self.uo, codigo="701", status="ativa")
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            email="u@test.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.bem = BemPatrimonial.objects.create(
            nome="Bem Teste",
            descricao="Desc",
            valor_unitario=Decimal("100.00"),
            marca="M",
            modelo="X",
            numero_patrimonial="001.000000001-0",
            unidade_administrativa=self.ua,
            criado_por=self.user,
            status=constants.APROVADO,
        )
        self.format = PDFFormat()

    def test_get_title(self):
        self.assertEqual(self.format.get_title(), "pdf")

    def test_create_dataset_levanta_not_implemented(self):
        with self.assertRaises(NotImplementedError) as ctx:
            self.format.create_dataset(BytesIO())
        self.assertIn("Importação", str(ctx.exception))

    def test_can_import_false(self):
        self.assertFalse(self.format.can_import())

    def test_can_export_true(self):
        self.assertTrue(self.format.can_export())

    def test_is_binary_true(self):
        self.assertTrue(self.format.is_binary())

    def test_get_read_mode(self):
        self.assertEqual(self.format.get_read_mode(), "rb")

    def test_get_extension(self):
        self.assertEqual(self.format.get_extension(), "pdf")

    def test_get_content_type(self):
        self.assertEqual(self.format.get_content_type(), "application/pdf")

    @patch.object(PDFFormat, "_criar_cabecalho")
    @patch.object(PDFFormat, "_criar_info_relatorio")
    @patch.object(PDFFormat, "_criar_tabela_bens")
    @patch.object(PDFFormat, "_criar_resumo")
    @patch.object(PDFFormat, "_criar_rodape")
    def test_export_data_retorna_bytes(
        self, mock_rodape, mock_resumo, mock_tabela, mock_info, mock_cabecalho
    ):
        mock_cabecalho.return_value = []
        mock_info.return_value = []
        mock_tabela.return_value = []
        mock_resumo.return_value = []
        mock_rodape.return_value = []
        self.format._export_request = MagicMock()
        self.format._export_request.user = MagicMock()
        self.format._export_request.user.get_full_name.return_value = "User"
        self.format._export_request.user.username = "user"
        self.format._export_queryset = [self.bem]

        result = self.format.export_data(None)

        self.assertIsInstance(result, bytes)
        mock_cabecalho.assert_called_once()
        mock_tabela.assert_called_once_with([self.bem])

    def test_export_data_sem_queryset_lista_vazia(self):
        self.format._export_request = None
        self.format._export_queryset = None
        with patch.object(PDFFormat, "_criar_cabecalho") as mock_cab:
            with patch.object(PDFFormat, "_criar_info_relatorio") as mock_info:
                with patch.object(PDFFormat, "_criar_tabela_bens") as mock_tabela:
                    with patch.object(PDFFormat, "_criar_resumo") as mock_resumo:
                        with patch.object(PDFFormat, "_criar_rodape") as mock_rodape:
                            mock_cab.return_value = []
                            mock_info.return_value = []
                            mock_tabela.return_value = []
                            mock_resumo.return_value = []
                            mock_rodape.return_value = []
                            self.format.export_data(None)
                            mock_tabela.assert_called_once_with([])
