from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib import messages
from unittest.mock import patch
from django.contrib.auth.models import Group

from bem_patrimonial.models import (
    MovimentacaoBemPatrimonial,
    StatusBemPatrimonial,
)
from bem_patrimonial.constants import (
    APROVADO,
    BLOQUEADO,
    ENVIADA,
    ACEITA,
    CANCELADA,
)
from bem_patrimonial.admins.movimentacao_bem_patrimonial import (
    MovimentacaoBemPatrimonialAdmin,
    aprovar_solicitacao,
    rejeitar_solicitacao,
    cancelar_solicitacao,
)
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO

# Reutiliza setup existente (assumindo versão já atualizada p/ novo model)
from bem_patrimonial.tests.tests_movimentacao_bloqueio import SetupMovimentacaoData


class CancelamentoMovimentacaoTestCase(TestCase):
    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_destino)
        self.bem = setup.create_bem_patrimonial(self.operador_origem, self.ua_origem)

        self.movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

    def test_cancelar_movimentacao_muda_status_e_define_cancelado_por(self):
        self.assertEqual(self.movimentacao.status, ENVIADA)
        self.assertIsNone(self.movimentacao.cancelado_por)

        self.movimentacao.cancelar_solicitacao(self.gestor)
        self.movimentacao.refresh_from_db()

        self.assertEqual(self.movimentacao.status, CANCELADA)
        self.assertEqual(self.movimentacao.cancelado_por, self.gestor)

    def test_cancelar_movimentacao_desbloqueia_bem(self):
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, BLOQUEADO)

        self.movimentacao.cancelar_solicitacao(self.gestor)

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, APROVADO)

    def test_property_cancelada(self):
        self.assertFalse(self.movimentacao.cancelada)

        self.movimentacao.cancelar_solicitacao(self.gestor)
        self.movimentacao.refresh_from_db()

        self.assertTrue(self.movimentacao.cancelada)

    def test_apenas_movimentacao_enviada_pode_ser_cancelada(self):
        self.movimentacao.aprovar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ACEITA)

        self.movimentacao.cancelar_solicitacao(self.gestor)
        self.movimentacao.refresh_from_db()

        self.assertEqual(self.movimentacao.status, ACEITA)
        self.assertIsNone(self.movimentacao.cancelado_por)

    def test_idempotencia_cancelamento(self):
        self.movimentacao.cancelar_solicitacao(self.gestor)
        self.movimentacao.refresh_from_db()

        status_antes = self.movimentacao.status
        cancelado_por_antes = self.movimentacao.cancelado_por

        self.movimentacao.cancelar_solicitacao(self.gestor)
        self.movimentacao.refresh_from_db()

        self.assertEqual(self.movimentacao.status, status_antes)
        self.assertEqual(self.movimentacao.cancelado_por, cancelado_por_antes)


class ValidacoesCruzadasCancelamentoTestCase(TestCase):
    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_destino)
        self.bem = setup.create_bem_patrimonial(self.operador_origem, self.ua_origem)

        self.movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

    def test_nao_pode_aprovar_movimentacao_cancelada(self):
        self.movimentacao.cancelar_solicitacao(self.gestor)
        self.movimentacao.refresh_from_db()

        self.movimentacao.aprovar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        self.assertEqual(self.movimentacao.status, CANCELADA)
        self.assertIsNone(self.movimentacao.aprovado_por)

    def test_nao_pode_rejeitar_movimentacao_cancelada(self):
        self.movimentacao.cancelar_solicitacao(self.gestor)
        self.movimentacao.refresh_from_db()

        self.movimentacao.rejeitar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        self.assertEqual(self.movimentacao.status, CANCELADA)
        self.assertIsNone(self.movimentacao.rejeitado_por)


class AdminActionCancelamentoTestCase(TestCase):
    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_destino)
        self.bem = setup.create_bem_patrimonial(self.operador_origem, self.ua_origem)

        self.movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = MovimentacaoBemPatrimonialAdmin(
            MovimentacaoBemPatrimonial, self.site
        )

    def _create_request_with_messages(self, user):
        request = self.factory.post("/admin/")
        request.user = user
        setattr(request, "session", "session")
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    @patch(
        "bem_patrimonial.admins.movimentacao_bem_patrimonial.envia_email_solicitacao_movimentacao_cancelada"
    )
    def test_action_cancelar_envia_email(self, mock_email):
        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        cancelar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, CANCELADA)

        mock_email.assert_called_once()
        call_args = mock_email.call_args[0]
        self.assertEqual(call_args[0], self.bem)
        self.assertEqual(call_args[1], self.gestor)
        self.assertEqual(call_args[2], self.operador_origem.email)

    def test_action_cancelar_exibe_mensagem_sucesso(self):
        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        with patch(
            "bem_patrimonial.admins.movimentacao_bem_patrimonial.envia_email_solicitacao_movimentacao_cancelada"
        ):
            cancelar_solicitacao(self.admin, request, queryset)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        self.assertTrue(any("cancelada com sucesso" in msg for msg in mensagens))

    def test_action_cancelar_ja_cancelada_exibe_warning(self):
        self.movimentacao.cancelar_solicitacao(self.gestor)
        self.movimentacao.refresh_from_db()

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        with patch(
            "bem_patrimonial.admins.movimentacao_bem_patrimonial.envia_email_solicitacao_movimentacao_cancelada"
        ):
            cancelar_solicitacao(self.admin, request, queryset)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        self.assertTrue(
            any("já foi cancelada anteriormente" in msg for msg in mensagens)
        )

    def test_action_cancelar_ja_aprovada_exibe_warning(self):
        self.movimentacao.aprovar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        with patch(
            "bem_patrimonial.admins.movimentacao_bem_patrimonial.envia_email_solicitacao_movimentacao_cancelada"
        ):
            cancelar_solicitacao(self.admin, request, queryset)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        self.assertTrue(
            any("já foi aprovada e não pode ser cancelada" in msg for msg in mensagens)
        )

    def test_action_cancelar_ja_rejeitada_exibe_warning(self):
        self.movimentacao.rejeitar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        with patch(
            "bem_patrimonial.admins.movimentacao_bem_patrimonial.envia_email_solicitacao_movimentacao_cancelada"
        ):
            cancelar_solicitacao(self.admin, request, queryset)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        self.assertTrue(
            any("já foi rejeitada e não pode ser cancelada" in msg for msg in mensagens)
        )

    @patch(
        "bem_patrimonial.admins.movimentacao_bem_patrimonial.envia_email_solicitacao_movimentacao_aceita"
    )
    def test_action_aprovar_cancelada_exibe_erro(self, mock_email):
        self.movimentacao.cancelar_solicitacao(self.gestor)
        self.movimentacao.refresh_from_db()

        request = self._create_request_with_messages(self.operador_destino)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        self.assertTrue(
            any("foi cancelada e não pode ser aprovada" in msg for msg in mensagens)
        )
        mock_email.assert_not_called()

    @patch(
        "bem_patrimonial.admins.movimentacao_bem_patrimonial.envia_email_solicitacao_movimentacao_rejeitada"
    )
    def test_action_rejeitar_cancelada_exibe_erro(self, mock_email):
        self.movimentacao.cancelar_solicitacao(self.gestor)
        self.movimentacao.refresh_from_db()

        request = self._create_request_with_messages(self.operador_destino)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        rejeitar_solicitacao(self.admin, request, queryset)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        self.assertTrue(
            any("foi cancelada e não pode ser rejeitada" in msg for msg in mensagens)
        )
        mock_email.assert_not_called()

    def test_action_cancelamento_visivel_para_todos(self):
        request = self._create_request_with_messages(self.gestor)
        actions = self.admin.get_actions(request)
        self.assertIn("cancelar_solicitacao", actions)

        request_operador = self._create_request_with_messages(self.operador_origem)
        actions_operador = self.admin.get_actions(request_operador)
        self.assertIn("cancelar_solicitacao", actions_operador)

    def test_operador_nao_cancela_movimentacao_de_outro(self):
        bem2 = SetupMovimentacaoData().create_bem_patrimonial(
            self.operador_destino, self.ua_origem
        )
        movimentacao2 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem2,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_destino,
        )
        request_operador = self._create_request_with_messages(self.operador_origem)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=movimentacao2.pk)
        with patch(
            "bem_patrimonial.admins.movimentacao_bem_patrimonial.envia_email_solicitacao_movimentacao_cancelada"
        ):
            cancelar_solicitacao(self.admin, request_operador, queryset)
        movimentacao2.refresh_from_db()

        self.assertEqual(movimentacao2.status, ENVIADA)

    @patch(
        "bem_patrimonial.admins.movimentacao_bem_patrimonial.envia_email_solicitacao_movimentacao_cancelada"
    )
    def test_action_cancelar_multiplas_movimentacoes(self, mock_email):
        bem2 = SetupMovimentacaoData().create_bem_patrimonial(
            self.operador_origem, self.ua_origem
        )
        movimentacao2 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem2,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(
            pk__in=[self.movimentacao.pk, movimentacao2.pk]
        )

        cancelar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        movimentacao2.refresh_from_db()

        self.assertEqual(self.movimentacao.status, CANCELADA)
        self.assertEqual(movimentacao2.status, CANCELADA)

        self.bem.refresh_from_db()
        bem2.refresh_from_db()
        self.assertEqual(self.bem.status, APROVADO)
        self.assertEqual(bem2.status, APROVADO)

        self.assertEqual(mock_email.call_count, 2)


class FluxoCancelamentoTestCase(TestCase):
    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_destino)
        self.bem = setup.create_bem_patrimonial(self.operador_origem, self.ua_origem)

    def test_cancelar_e_criar_nova_movimentacao(self):
        mov1 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, BLOQUEADO)

        mov1.cancelar_solicitacao(self.gestor)
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, APROVADO)

        mov2 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, BLOQUEADO)
        self.assertTrue(self.bem.tem_movimentacao_pendente)

        mov2.aprovar_solicitacao(self.operador_destino)
        self.bem.refresh_from_db()

        # Como não há mais gestão de quantidades por UA, validamos a troca de UA do bem
        self.assertEqual(self.bem.unidade_administrativa, self.ua_destino)

    def test_historico_status_ao_cancelar(self):
        count_inicial = StatusBemPatrimonial.objects.filter(
            bem_patrimonial=self.bem
        ).count()

        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, BLOQUEADO)

        count_apos_bloqueio = StatusBemPatrimonial.objects.filter(
            bem_patrimonial=self.bem
        ).count()
        self.assertEqual(count_apos_bloqueio, count_inicial + 1)

        ultimo_status = StatusBemPatrimonial.objects.filter(
            bem_patrimonial=self.bem
        ).last()
        self.assertEqual(ultimo_status.status, BLOQUEADO)
        self.assertIn(str(mov.pk), ultimo_status.observacao)

        mov.cancelar_solicitacao(self.gestor)
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, APROVADO)

        mov.refresh_from_db()
        self.assertEqual(mov.status, CANCELADA)
        self.assertEqual(mov.cancelado_por, self.gestor)


class EmailCancelamentoTestCase(TestCase):
    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_destino)

        self.gestor.nome = "José Teste"
        self.gestor.save()
        self.operador_origem.nome = "João Teste"
        self.operador_origem.save()
        self.bem = setup.create_bem_patrimonial(self.operador_origem, self.ua_origem)

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_email_contem_nome_gestor(self, mock_send_email):
        from bem_patrimonial.emails import (
            envia_email_solicitacao_movimentacao_cancelada,
        )

        envia_email_solicitacao_movimentacao_cancelada(
            self.bem, self.gestor, self.operador_origem.email
        )

        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args[0]
        dict_param = call_args[1]

        self.assertIn("José Teste", dict_param["subtitle"])
        self.assertIn(self.bem.nome, dict_param["subtitle"])

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_email_usa_username_como_fallback(self, mock_send_email):
        from bem_patrimonial.emails import (
            envia_email_solicitacao_movimentacao_cancelada,
        )

        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        gestor_sem_nome = Usuario.objects.create_user(
            username="gestor_sem_nome",
            email="gestor_sem_nome@test.com",
            password="test123",
            is_staff=True,
            unidade_administrativa=self.ua_origem,
        )
        gestor_sem_nome.groups.add(grupo_gestor)

        envia_email_solicitacao_movimentacao_cancelada(
            self.bem, gestor_sem_nome, self.operador_origem.email
        )

        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args[0]
        dict_param = call_args[1]

        self.assertIn("gestor_sem_nome", dict_param["subtitle"])
