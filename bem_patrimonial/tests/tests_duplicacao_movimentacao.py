import datetime
import threading
from django.test import TestCase, RequestFactory, TransactionTestCase
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import transaction, connection

from bem_patrimonial.models import (
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
)
from bem_patrimonial.constants import APROVADO
from bem_patrimonial.admins.movimentacao_bem_patrimonial import (
    MovimentacaoBemPatrimonialAdmin,
)
from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario
from usuario.constants import GRUPO_OPERADOR_INVENTARIO
from django.contrib.auth.models import Group


class SetupDuplicacaoData:

    def create_unidades_administrativas(self):
        ua_origem = UnidadeAdministrativa.objects.create(
            nome="DRE Centro", codigo="DRE-CENTRO"
        )
        ua_destino = UnidadeAdministrativa.objects.create(
            nome="DRE Sul", codigo="DRE-SUL"
        )
        return ua_origem, ua_destino

    def create_usuario(self, ua_origem):
        grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)

        operador = Usuario.objects.create_user(
            username="operador_teste",
            email="operador@test.com",
            password="test123",
            unidade_administrativa=ua_origem,
        )
        operador.groups.add(grupo_operador)
        return operador

    def create_bem_patrimonial(self, criado_por, ua_origem):
        bem = BemPatrimonial.objects.create(
            nome="Computador Desktop",
            marca="Dell",
            modelo="OptiPlex 7090",
            descricao="Computador Dell OptiPlex",
            valor_unitario=4500.00,
            numero_processo="789012",
            criado_por=criado_por,
            status=APROVADO,
            unidade_administrativa=ua_origem,
        )

        return bem


class ValidacaoMovimentacaoPendenteTestCase(TestCase):

    def setUp(self):
        setup = SetupDuplicacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        self.operador = setup.create_usuario(self.ua_origem)
        self.bem = setup.create_bem_patrimonial(self.operador, self.ua_origem)

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

    def test_criar_primeira_movimentacao_sucesso(self):
        self.assertFalse(self.bem.tem_movimentacao_pendente)

        request = self._create_request_with_messages(self.operador)

        movimentacao = MovimentacaoBemPatrimonial(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
        )

        self.admin.save_model(request, movimentacao, None, False)

        self.assertIsNotNone(movimentacao.pk)
        self.assertEqual(movimentacao.solicitado_por, self.operador)
        self.assertEqual(MovimentacaoBemPatrimonial.objects.count(), 1)

    def test_bloquear_segunda_movimentacao_quando_existe_pendente(self):
        MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
        )

        self.assertTrue(self.bem.tem_movimentacao_pendente)

        request = self._create_request_with_messages(self.operador)

        movimentacao2 = MovimentacaoBemPatrimonial(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
        )

        self.admin.save_model(request, movimentacao2, None, False)

        self.assertIsNone(movimentacao2.pk)
        self.assertEqual(MovimentacaoBemPatrimonial.objects.count(), 1)

    def test_permitir_movimentacao_apos_aprovar_anterior(self):
        mov1 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
        )
        mov1.aprovar_solicitacao(self.operador)

        self.assertFalse(self.bem.tem_movimentacao_pendente)

        request = self._create_request_with_messages(self.operador)

        movimentacao2 = MovimentacaoBemPatrimonial(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
        )

        self.admin.save_model(request, movimentacao2, None, False)

        self.assertIsNotNone(movimentacao2.pk)
        self.assertEqual(MovimentacaoBemPatrimonial.objects.count(), 2)

    def test_permitir_movimentacao_apos_rejeitar_anterior(self):
        mov1 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
        )
        mov1.rejeitar_solicitacao(self.operador)

        self.assertFalse(self.bem.tem_movimentacao_pendente)

        request = self._create_request_with_messages(self.operador)

        movimentacao2 = MovimentacaoBemPatrimonial(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
        )

        self.admin.save_model(request, movimentacao2, None, False)

        self.assertIsNotNone(movimentacao2.pk)
        self.assertEqual(MovimentacaoBemPatrimonial.objects.count(), 2)


class LockTransacionalTestCase(TransactionTestCase):

    def setUp(self):
        setup = SetupDuplicacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        self.operador = setup.create_usuario(self.ua_origem)
        self.bem = setup.create_bem_patrimonial(self.operador, self.ua_origem)

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

    def test_lock_select_for_update_previne_race_condition(self):
        resultados = {"criadas": 0, "bloqueadas": 0}
        threads = []

        def criar_movimentacao():
            # Função executada por cada thread
            try:
                with transaction.atomic():
                    request = self._create_request_with_messages(self.operador)

                    movimentacao = MovimentacaoBemPatrimonial(
                        bem_patrimonial=self.bem,
                        unidade_administrativa_origem=self.ua_origem,
                        unidade_administrativa_destino=self.ua_destino,
                    )

                    self.admin.save_model(request, movimentacao, None, False)

                    if movimentacao.pk:
                        resultados["criadas"] += 1
                    else:
                        resultados["bloqueadas"] += 1
            except Exception:
                resultados["bloqueadas"] += 1
            finally:
                # IMPORTANTE: Fecha a conexão da thread para evitar vazamento
                connection.close()

        num_threads = 5
        for _ in range(num_threads):
            t = threading.Thread(target=criar_movimentacao)
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(
            resultados["criadas"], 1, "Apenas 1 movimentação deveria ser criada"
        )
        self.assertEqual(
            resultados["bloqueadas"],
            num_threads - 1,
            f"{num_threads - 1} tentativas deveriam ser bloqueadas",
        )

        self.assertEqual(MovimentacaoBemPatrimonial.objects.count(), 1)

    def test_property_tem_movimentacao_pendente_em_transacao(self):
        with transaction.atomic():
            bem = BemPatrimonial.objects.select_for_update().get(pk=self.bem.pk)
            self.assertFalse(bem.tem_movimentacao_pendente)

        MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
        )

        with transaction.atomic():
            bem = BemPatrimonial.objects.select_for_update().get(pk=self.bem.pk)
            self.assertTrue(bem.tem_movimentacao_pendente)


class EdicaoMovimentacaoTestCase(TestCase):

    def setUp(self):
        setup = SetupDuplicacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        self.operador = setup.create_usuario(self.ua_origem)
        self.bem = setup.create_bem_patrimonial(self.operador, self.ua_origem)

        self.movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
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

    def test_pode_editar_movimentacao_existente(self):
        request = self._create_request_with_messages(self.operador)

        self.movimentacao.observacao = "Observação editada"

        self.admin.save_model(request, self.movimentacao, None, True)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.observacao, "Observação editada")

    def test_edicao_nao_passa_por_validacao_lock(self):
        request = self._create_request_with_messages(self.operador)

        observacao_original = self.movimentacao.observacao
        self.movimentacao.observacao = "Nova observação"

        self.admin.save_model(request, self.movimentacao, None, True)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.observacao, "Nova observação")
        self.assertNotEqual(self.movimentacao.observacao, observacao_original)
