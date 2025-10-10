import datetime
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib import messages

from bem_patrimonial.models import (
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
    StatusBemPatrimonial,
    UnidadeAdministrativaBemPatrimonial,
)
from bem_patrimonial.constants import (
    APROVADO,
    BLOQUEADO,
    AGUARDANDO_APROVACAO,
    ENVIADA,
    ACEITA,
    REJEITADA,
)
from bem_patrimonial.admins.movimentacao_bem_patrimonial import (
    MovimentacaoBemPatrimonialAdmin,
    aprovar_solicitacao,
    rejeitar_solicitacao,
)
from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario
from usuario.constants import GRUPO_OPERADOR_INVENTARIO, GRUPO_GESTOR_PATRIMONIO
from django.contrib.auth.models import Group


class SetupMovimentacaoData:

    def create_unidades_administrativas(self):
        ua_origem = UnidadeAdministrativa.objects.create(
            nome="DRE Centro", codigo="DRE-CENTRO"
        )
        ua_destino = UnidadeAdministrativa.objects.create(
            nome="DRE Sul", codigo="DRE-SUL"
        )
        return ua_origem, ua_destino

    def create_usuarios(self, ua_origem, ua_destino):
        grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)

        operador_origem = Usuario.objects.create_user(
            username="operador_origem",
            email="operador.origem@test.com",
            password="test123",
            unidade_administrativa=ua_origem,
        )
        operador_origem.groups.add(grupo_operador)

        operador_destino = Usuario.objects.create_user(
            username="operador_destino",
            email="operador.destino@test.com",
            password="test123",
            unidade_administrativa=ua_destino,
        )
        operador_destino.groups.add(grupo_operador)

        gestor = Usuario.objects.create_user(
            username="gestor",
            email="gestor@test.com",
            password="test123",
            is_staff=True,
            is_superuser=True,
            unidade_administrativa=ua_origem,
        )
        gestor.groups.add(grupo_gestor)

        return operador_origem, operador_destino, gestor

    def create_bem_patrimonial(self, criado_por, ua_origem, quantidade=10):
        bem = BemPatrimonial.objects.create(
            nome="Notebook Dell",
            data_compra_entrega=datetime.date.today(),
            origem="aquisicao_direta",
            marca="Dell",
            modelo="Inspiron 15",
            quantidade=quantidade,
            descricao="Notebook Dell Inspiron 15",
            valor_unitario=3500.00,
            numero_processo=123456,
            autorizacao_no_doc_em=datetime.date.today(),
            numero_nibpm=111111,
            numero_cimbpm=222222,
            localizacao="Almoxarifado",
            criado_por=criado_por,
            status=APROVADO,
        )

        ua_bem, created = UnidadeAdministrativaBemPatrimonial.objects.get_or_create(
            bem_patrimonial=bem,
            unidade_administrativa=ua_origem,
            defaults={"quantidade": quantidade},
        )
        if not created:
            ua_bem.quantidade = quantidade
            ua_bem.save()

        return bem


class BloqueioAutomaticoTestCase(TestCase):

    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_destino)
        self.bem = setup.create_bem_patrimonial(
            self.operador_origem, self.ua_origem, quantidade=10
        )

    def test_bem_bloqueado_ao_criar_movimentacao(self):
        self.assertEqual(self.bem.status, APROVADO)

        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

        self.bem.refresh_from_db()

        self.assertEqual(self.bem.status, BLOQUEADO)
        self.assertEqual(movimentacao.status, ENVIADA)

    def test_historico_status_criado_ao_bloquear(self):
        count_antes = StatusBemPatrimonial.objects.filter(
            bem_patrimonial=self.bem
        ).count()

        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

        count_depois = StatusBemPatrimonial.objects.filter(
            bem_patrimonial=self.bem
        ).count()

        self.assertEqual(count_depois, count_antes + 1)

        ultimo_status = StatusBemPatrimonial.objects.filter(
            bem_patrimonial=self.bem
        ).last()
        self.assertEqual(ultimo_status.status, BLOQUEADO)
        self.assertEqual(ultimo_status.atualizado_por, self.operador_origem)
        self.assertIn(str(movimentacao.pk), ultimo_status.observacao)

    def test_property_tem_movimentacao_pendente(self):
        self.assertFalse(self.bem.tem_movimentacao_pendente)

        MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

        self.assertTrue(self.bem.tem_movimentacao_pendente)

    def test_property_pode_solicitar_movimentacao(self):
        self.assertTrue(self.bem.pode_solicitar_movimentacao)

        self.bem.status = BLOQUEADO
        self.bem.save()

        self.assertFalse(self.bem.pode_solicitar_movimentacao)


class AprovacaoMovimentacaoTestCase(TestCase):

    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_destino)
        self.bem = setup.create_bem_patrimonial(
            self.operador_origem, self.ua_origem, quantidade=10
        )

        self.movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

    def test_aprovar_movimentacao_atualiza_quantidades(self):
        ua_origem_qtd_antes = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_origem
        ).quantidade

        self.movimentacao.aprovar_solicitacao(self.operador_destino)

        ua_origem_qtd = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_origem
        ).quantidade
        ua_destino_qtd = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_destino
        ).quantidade

        self.assertEqual(ua_origem_qtd, ua_origem_qtd_antes - 5)
        self.assertEqual(ua_destino_qtd, 5)

    def test_aprovar_movimentacao_desbloqueia_bem(self):
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, BLOQUEADO)

        self.movimentacao.aprovar_solicitacao(self.operador_destino)

        self.bem.refresh_from_db()

        self.assertEqual(self.bem.status, APROVADO)

    def test_aprovar_movimentacao_muda_status(self):
        self.assertEqual(self.movimentacao.status, ENVIADA)

        self.movimentacao.aprovar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        self.assertEqual(self.movimentacao.status, ACEITA)
        self.assertEqual(self.movimentacao.aprovado_por, self.operador_destino)

    def test_property_aceita(self):
        self.assertFalse(self.movimentacao.aceita)

        self.movimentacao.aprovar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        self.assertTrue(self.movimentacao.aceita)

    def test_nao_pode_aprovar_movimentacao_ja_aprovada(self):
        self.movimentacao.aprovar_solicitacao(self.operador_destino)

        ua_origem_qtd = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_origem
        ).quantidade
        ua_destino_qtd = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_destino
        ).quantidade

        self.movimentacao.refresh_from_db()
        self.movimentacao.aprovar_solicitacao(self.gestor)

        ua_origem_qtd_depois = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_origem
        ).quantidade
        ua_destino_qtd_depois = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_destino
        ).quantidade

        self.assertEqual(ua_origem_qtd, ua_origem_qtd_depois)
        self.assertEqual(ua_destino_qtd, ua_destino_qtd_depois)


class RejeicaoMovimentacaoTestCase(TestCase):

    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_destino)
        self.bem = setup.create_bem_patrimonial(
            self.operador_origem, self.ua_origem, quantidade=10
        )

        self.movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

    def test_rejeitar_movimentacao_nao_altera_quantidades(self):
        ua_origem_qtd_antes = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_origem
        ).quantidade

        self.movimentacao.rejeitar_solicitacao(self.operador_destino)

        ua_origem_qtd = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_origem
        ).quantidade

        self.assertEqual(ua_origem_qtd, ua_origem_qtd_antes)

        self.assertFalse(
            UnidadeAdministrativaBemPatrimonial.objects.filter(
                bem_patrimonial=self.bem, unidade_administrativa=self.ua_destino
            ).exists()
        )

    def test_rejeitar_movimentacao_desbloqueia_bem(self):
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, BLOQUEADO)

        self.movimentacao.rejeitar_solicitacao(self.operador_destino)

        self.bem.refresh_from_db()

        self.assertEqual(self.bem.status, APROVADO)

    def test_rejeitar_movimentacao_muda_status(self):
        self.assertEqual(self.movimentacao.status, ENVIADA)

        self.movimentacao.rejeitar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        self.assertEqual(self.movimentacao.status, REJEITADA)
        self.assertEqual(self.movimentacao.rejeitado_por, self.operador_destino)

    def test_property_rejeitada(self):
        self.assertFalse(self.movimentacao.rejeitada)

        self.movimentacao.rejeitar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        self.assertTrue(self.movimentacao.rejeitada)


class PermissoesAdminActionsTestCase(TestCase):

    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_destino)
        self.bem = setup.create_bem_patrimonial(
            self.operador_origem, self.ua_origem, quantidade=10
        )

        self.movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
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

    def test_operador_origem_nao_pode_aprovar(self):
        request = self._create_request_with_messages(self.operador_origem)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ENVIADA)
        self.assertIsNone(self.movimentacao.aprovado_por)

    def test_operador_destino_pode_aprovar(self):
        request = self._create_request_with_messages(self.operador_destino)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ACEITA)
        self.assertEqual(self.movimentacao.aprovado_por, self.operador_destino)

    def test_gestor_pode_aprovar(self):
        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ACEITA)
        self.assertEqual(self.movimentacao.aprovado_por, self.gestor)

    def test_solicitante_nao_pode_aprovar_propria_solicitacao(self):
        UnidadeAdministrativaBemPatrimonial.objects.get_or_create(
            bem_patrimonial=self.bem,
            unidade_administrativa=self.ua_destino,
            defaults={"quantidade": 5},
        )

        movimentacao2 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_destino,
            unidade_administrativa_destino=self.ua_origem,
            quantidade=2,
            solicitado_por=self.operador_destino,
        )

        request = self._create_request_with_messages(self.operador_destino)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=movimentacao2.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        movimentacao2.refresh_from_db()
        self.assertEqual(movimentacao2.status, ENVIADA)
        self.assertIsNone(movimentacao2.aprovado_por)

    def test_action_com_multiplas_movimentacoes(self):
        bem2 = SetupMovimentacaoData().create_bem_patrimonial(
            self.gestor, self.ua_origem, quantidade=5
        )
        movimentacao2 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem2,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=2,
            solicitado_por=self.operador_origem,
        )

        request = self._create_request_with_messages(self.operador_destino)
        queryset = MovimentacaoBemPatrimonial.objects.filter(
            pk__in=[self.movimentacao.pk, movimentacao2.pk]
        )

        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        movimentacao2.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ACEITA)
        self.assertEqual(movimentacao2.status, ACEITA)

    def test_nao_pode_aprovar_movimentacao_ja_aprovada(self):
        self.movimentacao.aprovar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        self.assertTrue(
            any("já foi aprovada anteriormente" in msg for msg in mensagens)
        )

    def test_nao_pode_rejeitar_movimentacao_ja_rejeitada(self):
        self.movimentacao.rejeitar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        rejeitar_solicitacao(self.admin, request, queryset)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        self.assertTrue(
            any("já foi rejeitada anteriormente" in msg for msg in mensagens)
        )


class IntegracaoCompletaTestCase(TestCase):

    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_destino)
        self.bem = setup.create_bem_patrimonial(
            self.operador_origem, self.ua_origem, quantidade=10
        )

    def test_fluxo_completo_aprovacao(self):
        self.assertEqual(self.bem.status, APROVADO)
        self.assertFalse(self.bem.tem_movimentacao_pendente)

        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, BLOQUEADO)
        self.assertTrue(self.bem.tem_movimentacao_pendente)
        self.assertEqual(movimentacao.status, ENVIADA)

        movimentacao.aprovar_solicitacao(self.operador_destino)
        movimentacao.refresh_from_db()
        self.bem.refresh_from_db()

        self.assertEqual(movimentacao.status, ACEITA)
        self.assertEqual(self.bem.status, APROVADO)
        self.assertFalse(self.bem.tem_movimentacao_pendente)

        ua_origem_qtd = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_origem
        ).quantidade
        ua_destino_qtd = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_destino
        ).quantidade

        self.assertEqual(ua_origem_qtd, 5)
        self.assertEqual(ua_destino_qtd, 5)

    def test_fluxo_completo_rejeicao(self):
        ua_origem_qtd_inicial = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_origem
        ).quantidade

        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, BLOQUEADO)

        movimentacao.rejeitar_solicitacao(self.operador_destino)
        movimentacao.refresh_from_db()
        self.bem.refresh_from_db()

        self.assertEqual(movimentacao.status, REJEITADA)
        self.assertEqual(self.bem.status, APROVADO)
        self.assertFalse(self.bem.tem_movimentacao_pendente)

        ua_origem_qtd_final = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_origem
        ).quantidade

        self.assertEqual(ua_origem_qtd_inicial, ua_origem_qtd_final)

    def test_multiplas_movimentacoes_sequenciais(self):
        mov1 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=3,
            solicitado_por=self.operador_origem,
        )
        mov1.aprovar_solicitacao(self.operador_destino)

        self.bem.refresh_from_db()
        mov2 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=2,
            solicitado_por=self.operador_origem,
        )
        mov2.aprovar_solicitacao(self.operador_destino)

        ua_origem_qtd = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_origem
        ).quantidade
        ua_destino_qtd = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_destino
        ).quantidade

        self.assertEqual(ua_origem_qtd, 5)  # 10 - 3 - 2
        self.assertEqual(ua_destino_qtd, 5)  # 0 + 3 + 2
