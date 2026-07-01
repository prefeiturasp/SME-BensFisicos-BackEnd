# bem_patrimonial/tests/tests_laudo_avaliacao.py
#
# Testes do módulo laudo_avaliacao.py:
#   - gerar_pdf_laudo_avaliacao()
#   - http_response_laudo_avaliacao()
#   - Endpoint GET /api/baixa-fisica/{id}/gerar-laudo/
#   - Campo url_gerar_laudo no serializer de detalhe
#
# Segue o mesmo padrão de tests_baixa_fisica_api.py:
#   - Factories locais (criar_uo, criar_ua, criar_usuario, criar_bem, criar_baixa)
#   - BaseSetup / BaseAPISetup
#   - Mock de http_response_laudo_avaliacao nas chamadas ao ViewSet
#   - Testes unitários das funções de geração sem dependência de filesystem

from io import BytesIO
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group
from django.http import HttpResponse
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from dados_comuns.tests.auth_test_utils import auth_kwargs
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO

from bem_patrimonial.models import (
    BaixaFisicaBemPatrimonial,
    BaixaFisicaBensItem,
    BemPatrimonial,
)
from bem_patrimonial.api_serializers import BaixaFisicaBemPatrimonialDetailSerializer
from bem_patrimonial import constants


# ============================================================================
# HELPERS — idênticos aos de tests_baixa_fisica_api.py
# ============================================================================

def criar_usuario(username, uo, ua, grupos=None, **kwargs):
    user = Usuario.objects.create_user(
        username=username,
        email=f"{username}@test.com",
        **auth_kwargs("senha123"),
        unidade_administrativa=ua,
        unidade_orcamentaria=uo,
        **kwargs,
    )
    for grupo_nome in (grupos or []):
        grupo, _ = Group.objects.get_or_create(name=grupo_nome)
        user.groups.add(grupo)
    return user


def criar_bem(ua, criado_por, numero_patrimonial="000.000000001-0",
              status=constants.APROVADO, **kwargs):
    return BemPatrimonial.objects.create(
        nome=kwargs.pop("nome", "Notebook Dell"),
        descricao=kwargs.pop("descricao", "Notebook para testes"),
        valor_unitario=kwargs.pop("valor_unitario", 1000),
        marca=kwargs.pop("marca", "Dell"),
        modelo=kwargs.pop("modelo", "Latitude"),
        numero_processo=kwargs.pop("numero_processo", "PROC-TESTE"),
        numero_patrimonial=numero_patrimonial,
        unidade_administrativa=ua,
        criado_por=criado_por,
        status=status,
        **kwargs,
    )


def criar_baixa(ua, criado_por, status=constants.AGUARDANDO_ENVIO, **kwargs):
    return BaixaFisicaBemPatrimonial.objects.create(
        unidade_administrativa_origem=ua,
        numero_processo_baixa=kwargs.pop("numero_processo_baixa", "PROC-BX-001"),
        status=status,
        criado_por=criado_por,
        data_baixa=kwargs.pop("data_baixa", timezone.localdate()),
        **kwargs,
    )


class BaseSetup(TestCase):
    def setUp(self):
        self.uo = criar_uo(codigo="100", nome="UO Teste", sigla="UOT")
        self.ua = criar_ua(uo=self.uo, codigo="001", nome="UA Teste", sigla="UAT")
        self.ua2 = criar_ua(uo=self.uo, codigo="002", nome="UA Dois", sigla="UAD")

        self.gestor = criar_usuario(
            "gestor_laudo", self.uo, self.ua,
            grupos=[GRUPO_GESTOR_PATRIMONIO],
            is_staff=True,
        )
        self.operador = criar_usuario(
            "operador_laudo", self.uo, self.ua,
            grupos=[GRUPO_OPERADOR_INVENTARIO],
        )
        self.operador2 = criar_usuario(
            "operador2_laudo", self.uo, self.ua2,
            grupos=[GRUPO_OPERADOR_INVENTARIO],
        )

        self.bem = criar_bem(self.ua, self.operador)
        self.bem2 = criar_bem(
            self.ua, self.operador,
            numero_patrimonial="000.000000002-0",
            nome="Monitor LG",
            descricao="Monitor 24 polegadas",
        )


class BaseAPISetup(BaseSetup):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def action_url(self, pk, action):
        return reverse(f"baixas-fisicas-{action}", kwargs={"pk": pk})


# ============================================================================
# TESTES UNITÁRIOS — gerar_pdf_laudo_avaliacao()
# ============================================================================

class GerarPdfLaudoAvaliacaoTestCase(BaseSetup):
    """
    Testa a função gerar_pdf_laudo_avaliacao() diretamente,
    sem passar pela API. Verifica:
      - Retorna BytesIO com conteúdo PDF válido
      - Rejeita objetos do tipo errado
      - Rejeita baixas com status diferente de ACEITA
    """

    def _criar_baixa_aceita(self, **kwargs):
        baixa = criar_baixa(
            self.ua, self.operador,
            status=constants.ACEITA,
            numero_processo_baixa=kwargs.pop("numero_processo_baixa", "PROC-LAUDO-001"),
            **kwargs,
        )
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        return baixa

    @patch("bem_patrimonial.laudo_avaliacao.carregar_logo")
    def test_retorna_bytesio_com_conteudo_pdf(self, mock_logo):
        """PDF gerado deve ser um BytesIO não-vazio com header %PDF."""
        mock_logo.return_value = MagicMock(
            wrap=MagicMock(return_value=(50, 30)),
            drawOn=MagicMock(),
        )
        from bem_patrimonial.laudo_avaliacao import gerar_pdf_laudo_avaliacao

        baixa = self._criar_baixa_aceita()
        buffer = gerar_pdf_laudo_avaliacao(baixa)

        self.assertIsInstance(buffer, BytesIO)
        conteudo = buffer.getvalue()
        self.assertTrue(len(conteudo) > 0, "PDF não deve estar vazio")
        self.assertTrue(
            conteudo.startswith(b"%PDF"),
            "Conteúdo deve iniciar com o cabeçalho PDF",
        )

    @patch("bem_patrimonial.laudo_avaliacao.carregar_logo")
    def test_retorna_bytesio_com_multiplos_bens(self, mock_logo):
        """PDF com múltiplos bens deve ser gerado sem erros."""
        mock_logo.return_value = MagicMock(
            wrap=MagicMock(return_value=(50, 30)),
            drawOn=MagicMock(),
        )
        from bem_patrimonial.laudo_avaliacao import gerar_pdf_laudo_avaliacao

        baixa = self._criar_baixa_aceita(numero_processo_baixa="PROC-MULTI")
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem2)

        buffer = gerar_pdf_laudo_avaliacao(baixa)
        self.assertIsInstance(buffer, BytesIO)
        self.assertTrue(len(buffer.getvalue()) > 0)

    @patch("bem_patrimonial.laudo_avaliacao.carregar_logo")
    def test_retorna_bytesio_sem_bens(self, mock_logo):
        """PDF sem itens deve ser gerado sem erros (exibe mensagem vazia)."""
        mock_logo.return_value = MagicMock(
            wrap=MagicMock(return_value=(50, 30)),
            drawOn=MagicMock(),
        )
        from bem_patrimonial.laudo_avaliacao import gerar_pdf_laudo_avaliacao

        baixa = criar_baixa(
            self.ua, self.operador,
            status=constants.ACEITA,
            numero_processo_baixa="PROC-VAZIO",
        )
        # Nenhum item vinculado
        buffer = gerar_pdf_laudo_avaliacao(baixa)
        self.assertIsInstance(buffer, BytesIO)
        self.assertTrue(len(buffer.getvalue()) > 0)

    def test_rejeita_objeto_invalido(self):
        """Deve lançar ValidationError para objeto que não seja BaixaFisicaBemPatrimonial."""
        from django.core.exceptions import ValidationError
        from bem_patrimonial.laudo_avaliacao import gerar_pdf_laudo_avaliacao

        with self.assertRaises(ValidationError):
            gerar_pdf_laudo_avaliacao("objeto_invalido")

    def test_rejeita_status_solicitada(self):
        """Deve lançar ValidationError para baixa com status SOLICITADA."""
        from django.core.exceptions import ValidationError
        from bem_patrimonial.laudo_avaliacao import gerar_pdf_laudo_avaliacao

        baixa = criar_baixa(self.ua, self.operador, status=constants.SOLICITADA)
        with self.assertRaises(ValidationError):
            gerar_pdf_laudo_avaliacao(baixa)

    def test_rejeita_status_aguardando_envio(self):
        """Deve lançar ValidationError para baixa com status AGUARDANDO_ENVIO."""
        from django.core.exceptions import ValidationError
        from bem_patrimonial.laudo_avaliacao import gerar_pdf_laudo_avaliacao

        baixa = criar_baixa(self.ua, self.operador, status=constants.AGUARDANDO_ENVIO)
        with self.assertRaises(ValidationError):
            gerar_pdf_laudo_avaliacao(baixa)

    def test_rejeita_status_recusada(self):
        """Deve lançar ValidationError para baixa com status RECUSADA."""
        from django.core.exceptions import ValidationError
        from bem_patrimonial.laudo_avaliacao import gerar_pdf_laudo_avaliacao

        baixa = criar_baixa(self.ua, self.operador, status=constants.RECUSADA)
        with self.assertRaises(ValidationError):
            gerar_pdf_laudo_avaliacao(baixa)


# ============================================================================
# TESTES UNITÁRIOS — http_response_laudo_avaliacao()
# ============================================================================

class HttpResponseLaudoAvaliacaoTestCase(BaseSetup):
    """
    Testa o wrapper http_response_laudo_avaliacao():
      - Content-Type correto
      - Content-Disposition com filename correto
      - Corpo não vazio
    """

    @patch("bem_patrimonial.laudo_avaliacao.gerar_pdf_laudo_avaliacao")
    def test_retorna_httpresponse_pdf(self, mock_gerar):
        """Deve retornar HttpResponse com Content-Type application/pdf."""
        pdf_falso = BytesIO(b"%PDF-1.4 fake content")
        mock_gerar.return_value = pdf_falso

        from bem_patrimonial.laudo_avaliacao import http_response_laudo_avaliacao

        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        resp = http_response_laudo_avaliacao(baixa)

        self.assertIsInstance(resp, HttpResponse)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    @patch("bem_patrimonial.laudo_avaliacao.gerar_pdf_laudo_avaliacao")
    def test_content_disposition_contem_id_baixa(self, mock_gerar):
        """Content-Disposition deve conter o id da baixa no nome do arquivo."""
        mock_gerar.return_value = BytesIO(b"%PDF-fake")

        from bem_patrimonial.laudo_avaliacao import http_response_laudo_avaliacao

        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        resp = http_response_laudo_avaliacao(baixa)

        self.assertIn("attachment", resp["Content-Disposition"])
        self.assertIn(str(baixa.id), resp["Content-Disposition"])
        self.assertIn(".pdf", resp["Content-Disposition"])

    @patch("bem_patrimonial.laudo_avaliacao.gerar_pdf_laudo_avaliacao")
    def test_aceita_usuario_gerador_sem_repassar(self, mock_gerar):
        """
        http_response_laudo_avaliacao aceita usuario_gerador mas não o repassa
        para gerar_pdf_laudo_avaliacao (parâmetro removido desta função pelo
        Sonar — era unused). Verifica que a chamada ao gerar_pdf usa só a baixa.
        """
        mock_gerar.return_value = BytesIO(b"%PDF-fake")

        from bem_patrimonial.laudo_avaliacao import http_response_laudo_avaliacao

        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        # Não deve lançar TypeError mesmo recebendo usuario_gerador
        resp = http_response_laudo_avaliacao(baixa, usuario_gerador=self.gestor)

        # gerar_pdf é chamado apenas com a baixa (sem usuario_gerador)
        mock_gerar.assert_called_once_with(baixa)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    @patch("bem_patrimonial.laudo_avaliacao.gerar_pdf_laudo_avaliacao")
    def test_corpo_nao_vazio(self, mock_gerar):
        """Corpo da resposta deve ter conteúdo."""
        conteudo = b"%PDF-1.4 fake content for test"
        mock_gerar.return_value = BytesIO(conteudo)

        from bem_patrimonial.laudo_avaliacao import http_response_laudo_avaliacao

        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        resp = http_response_laudo_avaliacao(baixa)

        self.assertTrue(len(resp.content) > 0)


# ============================================================================
# TESTES DO ENDPOINT — GET /api/baixa-fisica/{id}/gerar-laudo/
# ============================================================================

class BaixaFisicaViewSetGerarLaudoTestCase(BaseAPISetup):
    """
    Testa o endpoint gerar-laudo via API.
    Segue o mesmo padrão de BaixaFisicaViewSetGerarNbbpmTestCase.
    A geração real de PDF é mockada para isolar o teste da API.
    """

    def setUp(self):
        super().setUp()
        self.baixa_aceita = criar_baixa(
            self.ua, self.operador,
            status=constants.ACEITA,
            numero_processo_baixa="PROC-LAUDO-API",
        )
        BaixaFisicaBensItem.objects.create(baixa=self.baixa_aceita, bem=self.bem)

    # ── Casos de sucesso ────────────────────────────────────────────────────

    @patch("bem_patrimonial.api_views.http_response_laudo_avaliacao")
    def test_gerar_laudo_baixa_aceita_retorna_200(self, mock_pdf):
        """Endpoint deve retornar 200 para baixa com status ACEITA."""
        mock_pdf.return_value = HttpResponse(
            content=b"%PDF-fake",
            content_type="application/pdf",
        )
        self._auth(self.operador)
        resp = self.client.get(self.action_url(self.baixa_aceita.id, "gerar-laudo"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @patch("bem_patrimonial.api_views.http_response_laudo_avaliacao")
    def test_gerar_laudo_chama_funcao_com_baixa_correta(self, mock_pdf):
        """http_response_laudo_avaliacao deve ser chamado com a baixa correta."""
        mock_pdf.return_value = HttpResponse(
            content=b"%PDF-fake",
            content_type="application/pdf",
        )
        self._auth(self.operador)
        self.client.get(self.action_url(self.baixa_aceita.id, "gerar-laudo"))

        self.assertTrue(mock_pdf.called)
        args, kwargs = mock_pdf.call_args
        baixa_passada = args[0]
        self.assertEqual(baixa_passada.id, self.baixa_aceita.id)

    @patch("bem_patrimonial.api_views.http_response_laudo_avaliacao")
    def test_gerar_laudo_operador_pode_gerar(self, mock_pdf):
        """Operador de Inventário também pode gerar o laudo."""
        mock_pdf.return_value = HttpResponse(
            content=b"%PDF-fake",
            content_type="application/pdf",
        )
        self._auth(self.operador)
        resp = self.client.get(self.action_url(self.baixa_aceita.id, "gerar-laudo"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @patch("bem_patrimonial.api_views.http_response_laudo_avaliacao")
    def test_gerar_laudo_gestor_pode_gerar(self, mock_pdf):
        """Gestor de Patrimônio também pode gerar o laudo."""
        mock_pdf.return_value = HttpResponse(
            content=b"%PDF-fake",
            content_type="application/pdf",
        )
        self._auth(self.gestor)
        resp = self.client.get(self.action_url(self.baixa_aceita.id, "gerar-laudo"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # ── Casos de erro — status inválido ────────────────────────────────────

    def test_gerar_laudo_status_solicitada_retorna_400(self):
        """Deve retornar 400 para baixa com status SOLICITADA."""
        baixa = criar_baixa(
            self.ua, self.operador,
            status=constants.SOLICITADA,
            numero_processo_baixa="PROC-SOL",
        )
        self._auth(self.operador)
        resp = self.client.get(self.action_url(baixa.id, "gerar-laudo"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_gerar_laudo_status_aguardando_envio_retorna_400(self):
        """Deve retornar 400 para baixa com status AGUARDANDO_ENVIO."""
        baixa = criar_baixa(
            self.ua, self.operador,
            status=constants.AGUARDANDO_ENVIO,
            numero_processo_baixa="PROC-AG",
        )
        self._auth(self.operador)
        resp = self.client.get(self.action_url(baixa.id, "gerar-laudo"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_gerar_laudo_status_recusada_retorna_400(self):
        """Deve retornar 400 para baixa com status RECUSADA."""
        baixa = criar_baixa(
            self.ua, self.operador,
            status=constants.RECUSADA,
            numero_processo_baixa="PROC-REC",
        )
        self._auth(self.operador)
        resp = self.client.get(self.action_url(baixa.id, "gerar-laudo"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_gerar_laudo_mensagem_erro_status_invalido(self):
        """Resposta 400 deve conter mensagem de erro descritiva."""
        baixa = criar_baixa(
            self.ua, self.operador,
            status=constants.SOLICITADA,
            numero_processo_baixa="PROC-MSG",
        )
        self._auth(self.operador)
        resp = self.client.get(self.action_url(baixa.id, "gerar-laudo"))
        self.assertIn("detail", resp.data)

    # ── Casos de erro — acesso / escopo ───────────────────────────────────

    def test_gerar_laudo_nao_autenticado_retorna_401(self):
        """Requisição sem autenticação deve retornar 401."""
        resp = self.client.get(self.action_url(self.baixa_aceita.id, "gerar-laudo"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_gerar_laudo_outra_ua_retorna_404(self):
        """Operador de outra UA não deve conseguir gerar o laudo (fora do escopo)."""
        self._auth(self.operador2)
        resp = self.client.get(self.action_url(self.baixa_aceita.id, "gerar-laudo"))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_gerar_laudo_inexistente_retorna_404(self):
        """Baixa inexistente deve retornar 404."""
        self._auth(self.operador)
        resp = self.client.get(self.action_url(99999, "gerar-laudo"))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ============================================================================
# TESTES DO SERIALIZER — campo url_gerar_laudo
# ============================================================================

class BaixaFisicaDetailSerializerUrlGerarLaudoTestCase(BaseSetup):
    """
    Testa o campo url_gerar_laudo no BaixaFisicaBemPatrimonialDetailSerializer.
    Segue o padrão de BaixaFisicaDetailSerializerUrlsTestCase.
    """

    def _serializer(self, baixa, user=None):
        req = MagicMock()
        req.user = user or self.gestor
        req.build_absolute_uri = lambda path: f"https://testserver{path}"
        return BaixaFisicaBemPatrimonialDetailSerializer(
            baixa, context={"request": req}
        )

    def test_url_gerar_laudo_presente_quando_aceita(self):
        """url_gerar_laudo deve ser não-nulo para baixas com status ACEITA."""
        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        data = self._serializer(baixa).data
        self.assertIn("url_gerar_laudo", data)
        self.assertIsNotNone(data["url_gerar_laudo"])

    def test_url_gerar_laudo_contem_endpoint_correto(self):
        """url_gerar_laudo deve apontar para o endpoint gerar-laudo."""
        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        data = self._serializer(baixa).data
        self.assertIn("gerar-laudo", data["url_gerar_laudo"])

    def test_url_gerar_laudo_ausente_quando_solicitada(self):
        """url_gerar_laudo deve ser None para status SOLICITADA."""
        baixa = criar_baixa(self.ua, self.operador, status=constants.SOLICITADA)
        data = self._serializer(baixa).data
        self.assertIsNone(data["url_gerar_laudo"])

    def test_url_gerar_laudo_ausente_quando_aguardando_envio(self):
        """url_gerar_laudo deve ser None para status AGUARDANDO_ENVIO."""
        baixa = criar_baixa(self.ua, self.operador, status=constants.AGUARDANDO_ENVIO)
        data = self._serializer(baixa).data
        self.assertIsNone(data["url_gerar_laudo"])

    def test_url_gerar_laudo_ausente_quando_recusada(self):
        """url_gerar_laudo deve ser None para status RECUSADA."""
        baixa = criar_baixa(self.ua, self.operador, status=constants.RECUSADA)
        data = self._serializer(baixa).data
        self.assertIsNone(data["url_gerar_laudo"])

    def test_url_gerar_laudo_independe_de_numero_nbbpm(self):
        """
        url_gerar_laudo não depende de numero_nbbpm — ao contrário de
        url_gerar_nbbpm, o laudo pode ser gerado mesmo sem NBBPM.
        """
        # Sem NBBPM
        baixa_sem_nbbpm = criar_baixa(
            self.ua, self.operador,
            status=constants.ACEITA,
            numero_processo_baixa="PROC-SEM-NBBPM",
        )
        data_sem = self._serializer(baixa_sem_nbbpm).data
        self.assertIsNotNone(data_sem["url_gerar_laudo"])

        # Com NBBPM
        baixa_com_nbbpm = criar_baixa(
            self.ua, self.operador,
            status=constants.ACEITA,
            numero_nbbpm="NBBPM-TEST-001",
            numero_processo_baixa="PROC-COM-NBBPM",
        )
        data_com = self._serializer(baixa_com_nbbpm).data
        self.assertIsNotNone(data_com["url_gerar_laudo"])

    def test_url_gerar_nbbpm_ainda_exige_numero_nbbpm(self):
        """
        Confirma que url_gerar_nbbpm ainda exige numero_nbbpm (sem regressão).
        """
        baixa_sem_nbbpm = criar_baixa(
            self.ua, self.operador,
            status=constants.ACEITA,
            numero_processo_baixa="PROC-REG",
        )
        data = self._serializer(baixa_sem_nbbpm).data
        # O laudo não precisa de NBBPM...
        self.assertIsNotNone(data["url_gerar_laudo"])
        # ...mas o NBBPM ainda depende do número
        self.assertIsNone(data["url_gerar_nbbpm"])

    def test_url_gerar_laudo_sem_request_retorna_none(self):
        """Sem request no contexto, url_gerar_laudo deve ser None."""
        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        serializer = BaixaFisicaBemPatrimonialDetailSerializer(
            baixa, context={}
        )
        data = serializer.data
        self.assertIsNone(data["url_gerar_laudo"])

    def test_campo_url_gerar_laudo_presente_na_resposta(self):
        """Garante que o campo existe na resposta do serializer."""
        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        data = self._serializer(baixa).data
        self.assertIn("url_gerar_laudo", data)


# ============================================================================
# TESTES DE HELPERS INTERNOS — funções de formatação
# ============================================================================

class LaudoAvaliacaoHelpersTestCase(BaseSetup):
    """
    Testa as funções auxiliares do módulo sem gerar PDF,
    para cobrir casos extremos de dados.
    """

    def test_formatar_data_criacao_datetime_aware(self):
        """Deve formatar datetime-aware para DD/MM/AAAA."""
        from bem_patrimonial.laudo_avaliacao import _formatar_data_criacao

        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        resultado = _formatar_data_criacao(baixa)

        self.assertRegex(resultado, r"^\d{2}/\d{2}/\d{4}$")

    def test_formatar_data_criacao_none(self):
        """Quando data_criacao for None, deve retornar '-'."""
        from bem_patrimonial.laudo_avaliacao import _formatar_data_criacao

        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        baixa.data_criacao = None
        resultado = _formatar_data_criacao(baixa)

        self.assertEqual(resultado, "-")

    def test_obter_bens_baixa_ordenado_por_numero_patrimonial(self):
        """Bens devem ser retornados ordenados pelo número patrimonial."""
        from bem_patrimonial.laudo_avaliacao import _obter_bens_baixa

        baixa = criar_baixa(
            self.ua, self.operador,
            status=constants.ACEITA,
            numero_processo_baixa="PROC-ORD",
        )
        # Adiciona bens fora de ordem
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem2)  # 000.000000002-0
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)   # 000.000000001-0

        bens = _obter_bens_baixa(baixa)

        self.assertEqual(len(bens), 2)
        self.assertEqual(bens[0].numero_patrimonial, self.bem.numero_patrimonial)
        self.assertEqual(bens[1].numero_patrimonial, self.bem2.numero_patrimonial)

    def test_obter_bens_baixa_sem_itens_retorna_lista_vazia(self):
        """Baixa sem itens deve retornar lista vazia."""
        from bem_patrimonial.laudo_avaliacao import _obter_bens_baixa

        baixa = criar_baixa(
            self.ua, self.operador,
            status=constants.ACEITA,
            numero_processo_baixa="PROC-VAZIO",
        )
        bens = _obter_bens_baixa(baixa)
        self.assertEqual(bens, [])

    def test_obter_bens_baixa_ignora_itens_sem_bem(self):
        """Itens com bem=None devem ser ignorados silenciosamente."""
        from bem_patrimonial.laudo_avaliacao import _obter_bens_baixa

        baixa = criar_baixa(
            self.ua, self.operador,
            status=constants.ACEITA,
            numero_processo_baixa="PROC-NULL",
        )
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        # Simula um item sem bem via mock
        item_mock = MagicMock()
        item_mock.bem = None

        with patch.object(
            baixa.itens,
            "select_related",
            return_value=[
                MagicMock(bem=self.bem),
                item_mock,
            ],
        ):
            bens = _obter_bens_baixa(baixa)

        # Apenas o bem real deve aparecer
        self.assertEqual(len(bens), 1)
        self.assertEqual(bens[0], self.bem)
