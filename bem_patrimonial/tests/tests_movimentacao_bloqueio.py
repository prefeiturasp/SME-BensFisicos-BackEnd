import datetime
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib import messages

from bem_patrimonial.models import (
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
    StatusBemPatrimonial,
)
from bem_patrimonial.constants import (
    APROVADO,
    BLOQUEADO,
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

    def create_bem_patrimonial(
        self,
        criado_por,
        ua_origem,
        *,
        numero_patrimonial=None,
        sem_numeracao=False,
    ):
        # Se não for sem_numeracao e não passar número, gera o próximo disponível
        if numero_patrimonial is None and not sem_numeracao:
            base = 1
            while True:
                candidato = f"000.{str(base).zfill(12)}-0"
                if not BemPatrimonial.objects.filter(
                    numero_patrimonial=candidato
                ).exists():
                    numero_patrimonial = candidato
                    break
                base += 1

        bem = BemPatrimonial.objects.create(
            nome="Notebook Dell",
            descricao="Notebook Dell Inspiron 15",
            numero_processo="PROC-123456",
            valor_unitario=3500.00,
            marca="Dell",
            modelo="Inspiron 15",
            numero_patrimonial=numero_patrimonial,
            numero_formato_antigo=False,
            sem_numeracao=sem_numeracao,
            localizacao="Almoxarifado",
            criado_por=criado_por,
            status=APROVADO,
            unidade_administrativa=ua_origem,
        )
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
        self.bem = setup.create_bem_patrimonial(self.operador_origem, self.ua_origem)

    def test_bem_bloqueado_ao_criar_movimentacao(self):
        self.assertEqual(self.bem.status, APROVADO)

        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
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
        self.bem = setup.create_bem_patrimonial(self.operador_origem, self.ua_origem)

        self.movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

    def test_aprovar_movimentacao_move_bem_para_ua_destino(self):
        # Aprovação deve mover a UA do bem para o destino
        self.movimentacao.aprovar_solicitacao(self.operador_destino)

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.unidade_administrativa, self.ua_destino)

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
        # 1ª aprovação
        self.movimentacao.aprovar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()
        bem_ua_apos_primeira = self.bem.unidade_administrativa

        # 2ª tentativa não deve alterar nada
        self.movimentacao.aprovar_solicitacao(self.gestor)
        self.movimentacao.refresh_from_db()
        self.bem.refresh_from_db()

        self.assertEqual(self.movimentacao.aprovado_por, self.operador_destino)
        self.assertEqual(self.bem.unidade_administrativa, bem_ua_apos_primeira)


class RejeicaoMovimentacaoTestCase(TestCase):
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

    def test_rejeitar_movimentacao_nao_altera_ua_do_bem(self):
        ua_inicial = self.bem.unidade_administrativa

        self.movimentacao.rejeitar_solicitacao(self.operador_destino)
        self.bem.refresh_from_db()

        self.assertEqual(self.bem.unidade_administrativa, ua_inicial)

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
        # colocar o bem no destino para simular o operador_destino como "origem" de uma nova solicitação
        self.bem.set_unidade_administrative(self.ua_destino)

        movimentacao2 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_destino,
            unidade_administrativa_destino=self.ua_origem,
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
            self.gestor, self.ua_origem
        )
        movimentacao2 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem2,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
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
        self.bem = setup.create_bem_patrimonial(self.operador_origem, self.ua_origem)

    def test_fluxo_completo_aprovacao(self):
        self.assertEqual(self.bem.status, APROVADO)
        self.assertFalse(self.bem.tem_movimentacao_pendente)

        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
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
        # bem deve ir para a UA destino
        self.assertEqual(self.bem.unidade_administrativa, self.ua_destino)

    def test_fluxo_completo_rejeicao(self):
        ua_inicial = self.bem.unidade_administrativa

        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
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
        # bem deve permanecer na UA original
        self.assertEqual(self.bem.unidade_administrativa, ua_inicial)

    def test_multiplas_movimentacoes_sequenciais(self):
        # 1ª: origem -> destino
        mov1 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )
        mov1.aprovar_solicitacao(self.operador_destino)
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.unidade_administrativa, self.ua_destino)

        # 2ª: destino -> origem
        mov2 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_destino,
            unidade_administrativa_destino=self.ua_origem,
            solicitado_por=self.operador_destino,
        )
        mov2.aprovar_solicitacao(self.operador_origem)

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.unidade_administrativa, self.ua_origem)
