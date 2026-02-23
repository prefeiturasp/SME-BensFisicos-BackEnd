"""Testes para bem_patrimonial.emails."""
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone

from bem_patrimonial import emails
from bem_patrimonial.models import (
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
    BaixaFisicaBemPatrimonial,
    BaixaFisicaBensItem,
    StatusBemPatrimonial,
)
from bem_patrimonial import constants
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_OPERADOR_INVENTARIO
from django.contrib.auth.models import Group


class TestFormataListaBensBaixa(TestCase):
    """Testes para _formata_lista_bens_baixa."""

    def setUp(self):
        self.uo = criar_uo(codigo="601")
        self.ua = criar_ua(uo=self.uo, codigo="601", status=UnidadeAdministrativa.ATIVA)
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.bem = BemPatrimonial.objects.create(
            nome="Bem 1",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-1",
            numero_patrimonial="001.000000001-1",
            unidade_administrativa=self.ua,
            criado_por=self.user,
            status=constants.APROVADO,
        )

    def test_formata_lista_bens_baixa_com_itens(self):
        """_formata_lista_bens_baixa retorna lista formatada quando há itens."""
        baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua,
            numero_processo_baixa="PROC-1",
            status=constants.AGUARDANDO_ENVIO,
            criado_por=self.user,
            data_baixa=timezone.localdate(),
        )
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        result = emails._formata_lista_bens_baixa(baixa)
        self.assertIsNotNone(result)
        self.assertIn("001.000000001-1", result)
        self.assertIn("Bem 1", result)

    def test_formata_lista_bens_baixa_sem_itens(self):
        """_formata_lista_bens_baixa retorna None quando não há itens."""
        baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua,
            numero_processo_baixa="PROC-1",
            status=constants.AGUARDANDO_ENVIO,
            criado_por=self.user,
            data_baixa=timezone.localdate(),
        )
        result = emails._formata_lista_bens_baixa(baixa)
        self.assertIsNone(result)


class TestEnviaEmailCadastroNaoAprovado(TestCase):
    """Testes para envia_email_cadastro_nao_aprovado."""

    def setUp(self):
        self.uo = criar_uo(codigo="602")
        self.ua = criar_ua(uo=self.uo, codigo="602", status=UnidadeAdministrativa.ATIVA)
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            email="criador@test.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.bem = BemPatrimonial.objects.create(
            nome="Bem",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-1",
            unidade_administrativa=self.ua,
            criado_por=self.user,
            status=constants.AGUARDANDO_APROVACAO,
        )

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_envia_email_cadastro_nao_aprovado_chama_send(self, mock_send):
        """envia_email_cadastro_nao_aprovado chama send_email_ctrl (signal + chamada direta)."""
        status = StatusBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            status=constants.NAO_APROVADO,
            observacao="Ajustar documentação",
            atualizado_por=self.user,
        )
        emails.envia_email_cadastro_nao_aprovado(status)
        self.assertTrue(mock_send.called, "send_email_ctrl deve ser chamado")
        call_kw = mock_send.call_args
        self.assertEqual(call_kw[0][2], "simple_message.html")
        self.assertEqual(call_kw[0][3], self.user.email)


class TestEnviaEmailSolicitacaoMovimentacao(TestCase):
    """Testes para envia_email_solicitacao_movimentacao_aceita/rejeitada/cancelada."""

    def setUp(self):
        self.uo = criar_uo(codigo="603")
        self.ua_origem = criar_ua(uo=self.uo, codigo="603", status=UnidadeAdministrativa.ATIVA)
        self.ua_destino = criar_ua(uo=self.uo, codigo="604", status=UnidadeAdministrativa.ATIVA)
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        self.bem = BemPatrimonial.objects.create(
            nome="Bem",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-1",
            unidade_administrativa=self.ua_origem,
            criado_por=self.user,
            status=constants.APROVADO,
        )

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_envia_email_solicitacao_aceita(self, mock_send):
        """envia_email_solicitacao_movimentacao_aceita chama send_email_ctrl."""
        emails.envia_email_solicitacao_movimentacao_aceita(self.bem, ["dest@test.com"])
        mock_send.assert_called_once()
        self.assertIn("aceita", mock_send.call_args[0][0].lower())

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_envia_email_solicitacao_rejeitada(self, mock_send):
        """envia_email_solicitacao_movimentacao_rejeitada chama send_email_ctrl."""
        emails.envia_email_solicitacao_movimentacao_rejeitada(self.bem, ["dest@test.com"])
        mock_send.assert_called_once()
        self.assertIn("rejeitada", mock_send.call_args[0][0].lower())

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_envia_email_solicitacao_cancelada(self, mock_send):
        """envia_email_solicitacao_movimentacao_cancelada chama send_email_ctrl."""
        cancelador = Usuario.objects.create_user(
            username="cancelador",
            password="x",
            email="cancelador@test.com",
            nome="Cancelador",
        )
        emails.envia_email_solicitacao_movimentacao_cancelada(
            self.bem, cancelador, ["dest@test.com"]
        )
        mock_send.assert_called_once()
        self.assertIn("cancelada", mock_send.call_args[0][0].lower())


class TestEnviaEmailBaixaFisica(TestCase):
    """Testes para envia_email_baixa_fisica_*."""

    def setUp(self):
        self.uo = criar_uo(codigo="605")
        self.ua = criar_ua(uo=self.uo, codigo="605", status=UnidadeAdministrativa.ATIVA)
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            email="criador@test.com",
            nome="Criador",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.bem = BemPatrimonial.objects.create(
            nome="Bem",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-1",
            unidade_administrativa=self.ua,
            criado_por=self.user,
            status=constants.APROVADO,
        )

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_envia_email_baixa_fisica_aprovada_sem_criado_por_nao_envia(self, mock_send):
        """envia_email_baixa_fisica_aprovada não envia se criado_por sem email."""
        user_sem_email = Usuario.objects.create_user(
            username="seminemail",
            password="x",
            email="",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua,
            numero_processo_baixa="PROC-1",
            status=constants.ACEITA,
            criado_por=user_sem_email,
            data_baixa=timezone.localdate(),
        )
        emails.envia_email_baixa_fisica_aprovada(baixa)
        mock_send.assert_not_called()

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_envia_email_baixa_fisica_aprovada_com_criado_por_envia(self, mock_send):
        """envia_email_baixa_fisica_aprovada envia para criado_por."""
        baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua,
            numero_processo_baixa="PROC-1",
            status=constants.ACEITA,
            criado_por=self.user,
            data_baixa=timezone.localdate(),
        )
        emails.envia_email_baixa_fisica_aprovada(baixa)
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args[0][3], self.user.email)

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_envia_email_baixa_fisica_cancelada_sem_criado_por_nao_envia(self, mock_send):
        """envia_email_baixa_fisica_cancelada não envia se criado_por sem email."""
        user_sem_email = Usuario.objects.create_user(
            username="seminemail2",
            password="x",
            email="",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua,
            numero_processo_baixa="PROC-1",
            status=constants.RECUSADA,
            criado_por=user_sem_email,
            data_baixa=timezone.localdate(),
        )
        emails.envia_email_baixa_fisica_cancelada(baixa, self.user)
        mock_send.assert_not_called()


class TestEnviaEmailNovaSolicitacaoMovimentacao(TestCase):
    """Testes para envia_email_nova_solicitacao_movimentacao."""

    def setUp(self):
        self.uo = criar_uo(codigo="606")
        self.ua_origem = criar_ua(uo=self.uo, codigo="606", status=UnidadeAdministrativa.ATIVA)
        self.ua_destino = criar_ua(uo=self.uo, codigo="607", status=UnidadeAdministrativa.ATIVA)
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        self.bem = BemPatrimonial.objects.create(
            nome="Bem",
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="PROC-1",
            unidade_administrativa=self.ua_origem,
            criado_por=self.user,
            status=constants.APROVADO,
        )

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_envia_email_nova_solicitacao_sem_emails_nao_envia(self, mock_send):
        """envia_email_nova_solicitacao_movimentacao não envia se emails vazio."""
        mov = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.user,
            status=constants.ENVIADA,
        )
        from bem_patrimonial.models import MovimentacaoBensItem
        MovimentacaoBensItem.objects.create(movimentacao=mov, bem=self.bem)
        emails.envia_email_nova_solicitacao_movimentacao(mov, [])
        mock_send.assert_not_called()

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_envia_email_nova_solicitacao_com_emails_envia(self, mock_send):
        """envia_email_nova_solicitacao_movimentacao envia para lista de emails."""
        mov = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.user,
            status=constants.ENVIADA,
        )
        from bem_patrimonial.models import MovimentacaoBensItem
        MovimentacaoBensItem.objects.create(movimentacao=mov, bem=self.bem)
        emails.envia_email_nova_solicitacao_movimentacao(mov, ["destino@test.com"])
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args[0][3], ["destino@test.com"])
