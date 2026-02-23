"""Testes para dados_comuns.formats (UnidadeAdministrativaPDFFormat)."""
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.test import TestCase

from dados_comuns.formats import UnidadeAdministrativaPDFFormat
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo


class TestUnidadeAdministrativaPDFFormat(TestCase):
    """Testes para UnidadeAdministrativaPDFFormat."""

    def setUp(self):
        self.uo = criar_uo(codigo="701")
        self.ua1 = criar_ua(uo=self.uo, codigo="701", status=UnidadeAdministrativa.ATIVA)
        self.ua2 = criar_ua(uo=self.uo, codigo="702", status=UnidadeAdministrativa.INATIVA)
        self.format = UnidadeAdministrativaPDFFormat()

    def test_get_title(self):
        """get_title retorna 'pdf'."""
        self.assertEqual(self.format.get_title(), "pdf")

    def test_create_dataset_levanta_not_implemented(self):
        """create_dataset levanta NotImplementedError."""
        with self.assertRaises(NotImplementedError) as ctx:
            self.format.create_dataset(BytesIO())
        self.assertIn("Importação", str(ctx.exception))

    def test_can_import_false(self):
        """can_import retorna False."""
        self.assertFalse(self.format.can_import())

    def test_can_export_true(self):
        """can_export retorna True."""
        self.assertTrue(self.format.can_export())

    def test_is_binary_true(self):
        """is_binary retorna True."""
        self.assertTrue(self.format.is_binary())

    def test_get_read_mode(self):
        """get_read_mode retorna 'rb'."""
        self.assertEqual(self.format.get_read_mode(), "rb")

    def test_get_extension(self):
        """get_extension retorna 'pdf'."""
        self.assertEqual(self.format.get_extension(), "pdf")

    def test_get_content_type(self):
        """get_content_type retorna application/pdf."""
        self.assertEqual(self.format.get_content_type(), "application/pdf")

    @patch.object(UnidadeAdministrativaPDFFormat, "_criar_cabecalho")
    @patch.object(UnidadeAdministrativaPDFFormat, "_criar_tabela_unidades")
    def test_export_data_retorna_bytes(self, mock_tabela, mock_cabecalho):
        """export_data retorna bytes do PDF."""
        mock_cabecalho.return_value = []
        mock_tabela.return_value = []
        self.format._export_request = MagicMock()
        self.format._export_request.user = MagicMock()
        self.format._export_request.user.get_full_name.return_value = "Test User"
        self.format._export_request.user.username = "test"
        self.format._export_queryset = [self.ua1, self.ua2]

        result = self.format.export_data(None)

        self.assertIsInstance(result, bytes)
        mock_cabecalho.assert_called_once()
        mock_tabela.assert_called_once_with([self.ua1, self.ua2])

    def test_export_data_sem_queryset_usar_lista_vazia(self):
        """export_data sem _export_queryset usa lista vazia."""
        self.format._export_request = None
        self.format._export_queryset = None
        with patch.object(UnidadeAdministrativaPDFFormat, "_criar_cabecalho") as mock_cab:
            with patch.object(
                UnidadeAdministrativaPDFFormat, "_criar_tabela_unidades"
            ) as mock_tabela:
                mock_cab.return_value = []
                mock_tabela.return_value = []
                self.format.export_data(None)
                mock_tabela.assert_called_once_with([])
