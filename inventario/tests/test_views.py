"""Testes para inventario.views."""
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group
from django.test import TestCase, RequestFactory
from django.core.exceptions import PermissionDenied
from django.http import Http404

from inventario.views import download_conciliacao_pdf
from inventario.models import ConciliacaoUA
from inventario import constants
from dados_comuns.tests.factories import criar_ua, criar_uo
from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario
from usuario.constants import GRUPO_OPERADOR_INVENTARIO, GRUPO_GESTOR_PATRIMONIO


class TestDownloadConciliacaoPdf(TestCase):
    """Testes para download_conciliacao_pdf."""

    def setUp(self):
        self.factory = RequestFactory()
        self.uo = criar_uo(codigo="801")
        self.ua = criar_ua(uo=self.uo, codigo="801", status=UnidadeAdministrativa.ATIVA)
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.conciliacao = ConciliacaoUA.objects.create(
            numero_conciliacao="001.0001/2025",
            tipo=constants.CONCILIACAO_ANUAL,
            periodo_final=__import__("datetime").date(2025, 12, 31),
            unidade_administrativa=self.ua,
            status=constants.CONCILIACAO_EM_ABERTO,
        )

    def test_download_conciliacao_pdf_404_se_nao_existe(self):
        """download_conciliacao_pdf retorna 404 se conciliação não existe."""
        request = self.factory.get("/")
        request.user = self.user
        with self.assertRaises(Http404):
            download_conciliacao_pdf(request, pk=99999)

    @patch("inventario.views.gerar_pdf_conciliacao")
    def test_download_conciliacao_pdf_operador_outra_ua_permission_denied(
        self, mock_gerar
    ):
        """Operador de outra UA recebe PermissionDenied."""
        outra_ua = criar_ua(uo=self.uo, codigo="802", status=UnidadeAdministrativa.ATIVA)
        grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
        operador = Usuario.objects.create_user(
            username="operador",
            password="x",
            email="op@test.com",
            unidade_administrativa=outra_ua,
            unidade_orcamentaria=self.uo,
        )
        operador.groups.add(grupo_operador)
        request = self.factory.get("/")
        request.user = operador

        mock_gerar.return_value = MagicMock()
        mock_gerar.return_value.seek = MagicMock()

        with self.assertRaises(PermissionDenied):
            download_conciliacao_pdf(request, pk=self.conciliacao.pk)

    @patch("inventario.views.gerar_pdf_conciliacao")
    def test_download_conciliacao_pdf_gestor_permite(self, mock_gerar):
        """Gestor pode baixar PDF de qualquer conciliação."""
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.user.groups.add(grupo_gestor)

        mock_buffer = MagicMock()
        mock_buffer.seek = MagicMock()
        mock_gerar.return_value = mock_buffer

        request = self.factory.get("/")
        request.user = self.user

        response = download_conciliacao_pdf(request, pk=self.conciliacao.pk)

        self.assertEqual(response.status_code, 200)
        mock_gerar.assert_called_once()
        self.assertTrue(response["Content-Disposition"].startswith("attachment"))
        self.assertIn(".pdf", response["Content-Disposition"])
