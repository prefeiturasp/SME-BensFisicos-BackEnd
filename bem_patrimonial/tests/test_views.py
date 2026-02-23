"""Testes para bem_patrimonial.views."""
from unittest.mock import patch, MagicMock

from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory, TestCase

from bem_patrimonial.models import MovimentacaoBemPatrimonial
from bem_patrimonial import constants
from bem_patrimonial.views import download_documento_cimbpm
from dados_comuns.tests.factories import criar_ua
from usuario.models import Usuario
from usuario.constants import GRUPO_OPERADOR_INVENTARIO, GRUPO_GESTOR_PATRIMONIO


class TestDownloadDocumentoCimbpm(TestCase):
    """Testes para download_documento_cimbpm."""

    def setUp(self):
        self.factory = RequestFactory()
        self.uo = criar_ua(codigo="701").unidade_orcamentaria
        self.ua_origem = criar_ua(uo=self.uo, codigo="701", nome="UA O")
        self.ua_destino = criar_ua(uo=self.uo, codigo="702", nome="UA D")
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            email="u@test.com",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        self.mov = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.user,
            status=constants.ENVIADA,
            numero_cimbpm="CIMBPM.2025.001",
        )

    def test_404_se_movimentacao_nao_existe(self):
        """Retorna 404 se pk não existe."""
        request = self.factory.get("/")
        request.user = self.user
        with self.assertRaises(Http404):
            download_documento_cimbpm(request, pk=99999)

    def test_404_se_numero_cimbpm_vazio(self):
        """Retorna 404 se movimentação não tem numero_cimbpm."""
        self.mov.numero_cimbpm = ""
        self.mov.save(update_fields=["numero_cimbpm"])
        request = self.factory.get("/")
        request.user = self.user
        with self.assertRaises(Http404) as ctx:
            download_documento_cimbpm(request, pk=self.mov.pk)
        self.assertIn("CIMBPM", str(ctx.exception))

    @patch("bem_patrimonial.cimbpm.gerar_pdf_cimbpm")
    def test_operador_outra_ua_permission_denied(self, mock_gerar):
        """Operador (só inventário) de outra UA recebe PermissionDenied."""
        outra_ua = criar_ua(uo=self.uo, codigo="703", nome="Outra")
        grupo_op, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
        operador = Usuario.objects.create_user(
            username="operador",
            password="x",
            unidade_administrativa=outra_ua,
            unidade_orcamentaria=self.uo,
        )
        operador.groups.add(grupo_op)
        request = self.factory.get("/")
        request.user = operador
        with self.assertRaises(PermissionDenied):
            download_documento_cimbpm(request, pk=self.mov.pk)
        mock_gerar.assert_not_called()

    @patch("bem_patrimonial.cimbpm.gerar_pdf_cimbpm")
    def test_gestor_pode_baixar_qualquer_movimentacao(self, mock_gerar):
        """Gestor pode baixar documento de qualquer movimentação."""
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.user.groups.add(grupo_gestor)
        mock_buffer = MagicMock()
        mock_gerar.return_value = mock_buffer
        request = self.factory.get("/")
        request.user = self.user
        response = download_documento_cimbpm(request, pk=self.mov.pk)
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("CIMBPM", response["Content-Disposition"])
        mock_gerar.assert_called_once()

    @patch("bem_patrimonial.cimbpm.gerar_pdf_cimbpm")
    def test_operador_da_ua_origem_pode_baixar(self, mock_gerar):
        """Operador da UA de origem pode baixar."""
        grupo_op, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
        operador = Usuario.objects.create_user(
            username="op_origem",
            password="x",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        operador.groups.add(grupo_op)
        mock_buffer = MagicMock()
        mock_gerar.return_value = mock_buffer
        request = self.factory.get("/")
        request.user = operador
        response = download_documento_cimbpm(request, pk=self.mov.pk)
        self.assertEqual(response.status_code, 200)
        mock_gerar.assert_called_once()
