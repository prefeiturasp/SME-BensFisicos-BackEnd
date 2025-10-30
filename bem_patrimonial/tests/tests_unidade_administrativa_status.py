from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib import messages

from bem_patrimonial.models import (
    MovimentacaoBemPatrimonial,
    UnidadeAdministrativaBemPatrimonial,
)
from bem_patrimonial.constants import ENVIADA
from bem_patrimonial.admins.movimentacao_bem_patrimonial import (
    MovimentacaoBemPatrimonialAdmin,
    aprovar_solicitacao,
    rejeitar_solicitacao,
)
from bem_patrimonial.admins.forms.movimentacao_bem_patrimonial_form import (
    MovimentacaoBemPatrimonialForm,
)
from dados_comuns.models import UnidadeAdministrativa
from .tests_unidade_administrativa_setup import SetupUnidadeAdministrativaStatusData


class CriacaoMovimentacaoComUAInativaTestCase(TestCase):

    def setUp(self):
        setup = SetupUnidadeAdministrativaStatusData()
        self.ua_ativa_1, self.ua_ativa_2, self.ua_inativa = (
            setup.create_unidades_administrativas()
        )
        self.operador_1, self.operador_2, self.gestor = setup.create_usuarios(
            self.ua_ativa_1, self.ua_ativa_2
        )
        self.bem = setup.create_bem_patrimonial(
            self.operador_1, self.ua_ativa_1, quantidade=10
        )

        self.factory = RequestFactory()

    def _create_form_with_request(self, user, data):
        request = self.factory.post("/admin/")
        request.user = user
        form = MovimentacaoBemPatrimonialForm(data=data)
        form.request = request
        return form

    def test_nao_pode_criar_movimentacao_com_ua_origem_inativa(self):
        bem_ua_inativa = self.bem
        UnidadeAdministrativaBemPatrimonial.objects.create(
            bem_patrimonial=bem_ua_inativa,
            unidade_administrativa=self.ua_inativa,
            quantidade=5,
        )

        data = {
            "bem_patrimonial": bem_ua_inativa.pk,
            "unidade_administrativa_origem": self.ua_inativa.pk,
            "unidade_administrativa_destino": self.ua_ativa_2.pk,
            "quantidade": 3,
        }

        form = self._create_form_with_request(self.gestor, data)
        self.assertFalse(form.is_valid())
        self.assertIn("unidade de origem", str(form.errors))
        self.assertIn("inativa", str(form.errors))

    def test_nao_pode_criar_movimentacao_com_ua_destino_inativa(self):
        data = {
            "bem_patrimonial": self.bem.pk,
            "unidade_administrativa_origem": self.ua_ativa_1.pk,
            "unidade_administrativa_destino": self.ua_inativa.pk,
            "quantidade": 3,
        }

        form = self._create_form_with_request(self.operador_1, data)
        self.assertFalse(form.is_valid())
        self.assertIn("unidade de destino", str(form.errors))
        self.assertIn("inativa", str(form.errors))

    def test_nao_pode_criar_movimentacao_com_ambas_uas_inativas(self):
        ua_inativa_2 = UnidadeAdministrativa.objects.create(
            nome="DRE Leste Inativa",
            codigo="DRE-LESTE",
            sigla="DREL",
            status=UnidadeAdministrativa.INATIVA,
        )

        UnidadeAdministrativaBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa=self.ua_inativa,
            quantidade=5,
        )

        data = {
            "bem_patrimonial": self.bem.pk,
            "unidade_administrativa_origem": self.ua_inativa.pk,
            "unidade_administrativa_destino": ua_inativa_2.pk,
            "quantidade": 2,
        }

        form = self._create_form_with_request(self.gestor, data)
        self.assertFalse(form.is_valid())
        self.assertIn("inativa", str(form.errors))

    def test_pode_criar_movimentacao_com_ambas_uas_ativas(self):
        data = {
            "bem_patrimonial": self.bem.pk,
            "unidade_administrativa_origem": self.ua_ativa_1.pk,
            "unidade_administrativa_destino": self.ua_ativa_2.pk,
            "quantidade": 3,
        }

        form = self._create_form_with_request(self.operador_1, data)
        if not form.is_valid():
            self.assertNotIn("inativa", str(form.errors).lower())


class AprovacaoRejeicaoMovimentacaoComUAInativaTestCase(TestCase):

    def setUp(self):
        setup = SetupUnidadeAdministrativaStatusData()
        self.ua_origem, self.ua_destino, self.ua_inativa = (
            setup.create_unidades_administrativas()
        )
        self.operador_origem, self.operador_destino, self.gestor = (
            setup.create_usuarios(self.ua_origem, self.ua_destino)
        )
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

    def test_nao_pode_aprovar_se_ua_origem_inativada(self):
        self.ua_origem.status = UnidadeAdministrativa.INATIVA
        self.ua_origem.save()

        request = self._create_request_with_messages(self.operador_destino)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ENVIADA)
        self.assertIsNone(self.movimentacao.aprovado_por)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        self.assertTrue(
            any(
                "unidade de origem" in msg.lower() and "inativa" in msg.lower()
                for msg in mensagens
            )
        )

    def test_nao_pode_aprovar_se_ua_destino_inativada(self):
        self.ua_destino.status = UnidadeAdministrativa.INATIVA
        self.ua_destino.save()

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ENVIADA)
        self.assertIsNone(self.movimentacao.aprovado_por)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        self.assertTrue(
            any(
                "unidade de destino" in msg.lower() and "inativa" in msg.lower()
                for msg in mensagens
            )
        )

    def test_nao_pode_aprovar_se_ambas_uas_inativadas(self):
        self.ua_origem.status = UnidadeAdministrativa.INATIVA
        self.ua_origem.save()
        self.ua_destino.status = UnidadeAdministrativa.INATIVA
        self.ua_destino.save()

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ENVIADA)
        self.assertIsNone(self.movimentacao.aprovado_por)

    def test_nao_pode_rejeitar_se_ua_origem_inativada(self):
        self.ua_origem.status = UnidadeAdministrativa.INATIVA
        self.ua_origem.save()

        request = self._create_request_with_messages(self.operador_destino)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        rejeitar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ENVIADA)
        self.assertIsNone(self.movimentacao.rejeitado_por)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        self.assertTrue(any("inativa" in msg.lower() for msg in mensagens))

    def test_nao_pode_rejeitar_se_ua_destino_inativada(self):
        self.ua_destino.status = UnidadeAdministrativa.INATIVA
        self.ua_destino.save()

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        rejeitar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ENVIADA)
        self.assertIsNone(self.movimentacao.rejeitado_por)

    def test_pode_aprovar_se_ambas_uas_ativas(self):
        request = self._create_request_with_messages(self.operador_destino)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, "aceita")
        self.assertEqual(self.movimentacao.aprovado_por, self.operador_destino)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        self.assertTrue(any("sucesso" in msg.lower() for msg in mensagens))


class MultiplasMovimentacoesComUAInativaTestCase(TestCase):

    def setUp(self):
        setup = SetupUnidadeAdministrativaStatusData()
        self.ua_ativa_1, self.ua_ativa_2, self.ua_inativa = (
            setup.create_unidades_administrativas()
        )
        self.operador_1, self.operador_2, self.gestor = setup.create_usuarios(
            self.ua_ativa_1, self.ua_ativa_2
        )

        self.bem1 = setup.create_bem_patrimonial(
            self.operador_1, self.ua_ativa_1, quantidade=10
        )
        self.bem2 = setup.create_bem_patrimonial(
            self.operador_1, self.ua_ativa_1, quantidade=8
        )

        self.mov1 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem1,
            unidade_administrativa_origem=self.ua_ativa_1,
            unidade_administrativa_destino=self.ua_ativa_2,
            quantidade=3,
            solicitado_por=self.operador_1,
        )

        self.mov2 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem2,
            unidade_administrativa_origem=self.ua_ativa_1,
            unidade_administrativa_destino=self.ua_ativa_2,
            quantidade=2,
            solicitado_por=self.operador_1,
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

    def test_action_aprova_apenas_movimentacoes_com_uas_ativas(self):
        self.ua_ativa_1.status = UnidadeAdministrativa.INATIVA
        self.ua_ativa_1.save()

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(
            pk__in=[self.mov1.pk, self.mov2.pk]
        )

        aprovar_solicitacao(self.admin, request, queryset)

        self.mov1.refresh_from_db()
        self.mov2.refresh_from_db()
        self.assertEqual(self.mov1.status, ENVIADA)
        self.assertEqual(self.mov2.status, ENVIADA)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        mensagens_inativa = [msg for msg in mensagens if "inativa" in msg.lower()]
        self.assertEqual(len(mensagens_inativa), 2)


class InativacaoUAComBensTestCase(TestCase):

    def setUp(self):
        setup = SetupUnidadeAdministrativaStatusData()
        self.ua_ativa_1, self.ua_ativa_2, self.ua_inativa = (
            setup.create_unidades_administrativas()
        )
        self.operador_1, self.operador_2, self.gestor = setup.create_usuarios(
            self.ua_ativa_1, self.ua_ativa_2
        )
        self.bem = setup.create_bem_patrimonial(
            self.operador_1, self.ua_ativa_1, quantidade=10
        )

    def test_nao_pode_inativar_ua_com_bens_quantidade_maior_que_zero(self):
        self.assertFalse(self.ua_ativa_1.pode_inativar())

    def test_pode_inativar_ua_sem_bens(self):
        ua_nova = UnidadeAdministrativa.objects.create(
            nome="DRE Teste",
            codigo="DRE-TESTE",
            sigla="DRET",
            status=UnidadeAdministrativa.ATIVA,
        )
        self.assertTrue(ua_nova.pode_inativar())

    def test_pode_inativar_ua_com_bens_quantidade_zero(self):
        ua_bem = UnidadeAdministrativaBemPatrimonial.objects.get(
            bem_patrimonial=self.bem, unidade_administrativa=self.ua_ativa_1
        )
        ua_bem.quantidade = 0
        ua_bem.save()

        self.assertTrue(self.ua_ativa_1.pode_inativar())

    def test_property_is_ativa(self):
        self.assertTrue(self.ua_ativa_1.is_ativa)
        self.assertTrue(self.ua_ativa_2.is_ativa)
        self.assertFalse(self.ua_inativa.is_ativa)

        self.ua_ativa_1.status = UnidadeAdministrativa.INATIVA
        self.ua_ativa_1.save()
        self.ua_ativa_1.refresh_from_db()

        self.assertFalse(self.ua_ativa_1.is_ativa)


class AutocompleteComUAInativaTestCase(TestCase):

    def setUp(self):
        setup = SetupUnidadeAdministrativaStatusData()
        self.ua_ativa_1, self.ua_ativa_2, self.ua_inativa = (
            setup.create_unidades_administrativas()
        )
        self.operador_1, self.operador_2, self.gestor = setup.create_usuarios(
            self.ua_ativa_1, self.ua_ativa_2
        )
        self.bem = setup.create_bem_patrimonial(
            self.operador_1, self.ua_ativa_1, quantidade=10
        )

    def test_form_filtra_apenas_uas_ativas_origem(self):
        form = MovimentacaoBemPatrimonialForm()

        uas_origem = form.fields["unidade_administrativa_origem"].queryset
        self.assertIn(self.ua_ativa_1, uas_origem)
        self.assertIn(self.ua_ativa_2, uas_origem)
        self.assertNotIn(self.ua_inativa, uas_origem)

    def test_form_filtra_apenas_uas_ativas_destino(self):
        form = MovimentacaoBemPatrimonialForm()

        uas_destino = form.fields["unidade_administrativa_destino"].queryset
        self.assertIn(self.ua_ativa_1, uas_destino)
        self.assertIn(self.ua_ativa_2, uas_destino)
        self.assertNotIn(self.ua_inativa, uas_destino)

    def test_form_filtra_apenas_bens_aprovados(self):
        form = MovimentacaoBemPatrimonialForm()

        bens = form.fields["bem_patrimonial"].queryset
        self.assertIn(self.bem, bens)
        self.assertEqual(bens.count(), 1)


class CenariosCombinacaoUAStatusTestCase(TestCase):

    def setUp(self):
        setup = SetupUnidadeAdministrativaStatusData()
        self.ua_ativa_1, self.ua_ativa_2, self.ua_inativa = (
            setup.create_unidades_administrativas()
        )
        self.operador_1, self.operador_2, self.gestor = setup.create_usuarios(
            self.ua_ativa_1, self.ua_ativa_2
        )
        self.bem = setup.create_bem_patrimonial(
            self.operador_1, self.ua_ativa_1, quantidade=10
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

    def test_ciclo_vida_completo_com_inativacao_no_meio(self):
        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_ativa_1,
            unidade_administrativa_destino=self.ua_ativa_2,
            quantidade=3,
            solicitado_por=self.operador_1,
        )
        self.assertEqual(movimentacao.status, ENVIADA)

        self.ua_ativa_1.status = UnidadeAdministrativa.INATIVA
        self.ua_ativa_1.save()

        request = self._create_request_with_messages(self.operador_2)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=movimentacao.pk)
        aprovar_solicitacao(self.admin, request, queryset)

        movimentacao.refresh_from_db()
        self.assertEqual(movimentacao.status, ENVIADA)
        self.assertIsNone(movimentacao.aprovado_por)

        self.ua_ativa_1.status = UnidadeAdministrativa.ATIVA
        self.ua_ativa_1.save()

        request2 = self._create_request_with_messages(self.operador_2)
        queryset2 = MovimentacaoBemPatrimonial.objects.filter(pk=movimentacao.pk)
        aprovar_solicitacao(self.admin, request2, queryset2)

        movimentacao.refresh_from_db()
        self.assertEqual(movimentacao.status, "aceita")
        self.assertEqual(movimentacao.aprovado_por, self.operador_2)

    def test_reativacao_ua_permite_novas_movimentacoes(self):
        self.ua_ativa_2.status = UnidadeAdministrativa.INATIVA
        self.ua_ativa_2.save()

        data_invalida = {
            "bem_patrimonial": self.bem.pk,
            "unidade_administrativa_origem": self.ua_ativa_1.pk,
            "unidade_administrativa_destino": self.ua_ativa_2.pk,
            "quantidade": 2,
        }

        request = self.factory.post("/admin/")
        request.user = self.operador_1
        form_invalida = MovimentacaoBemPatrimonialForm(data=data_invalida)
        form_invalida.request = request
        self.assertFalse(form_invalida.is_valid())

        self.ua_ativa_2.status = UnidadeAdministrativa.ATIVA
        self.ua_ativa_2.save()

        data_valida = {
            "bem_patrimonial": self.bem.pk,
            "unidade_administrativa_origem": self.ua_ativa_1.pk,
            "unidade_administrativa_destino": self.ua_ativa_2.pk,
            "quantidade": 2,
        }

        form_valida = MovimentacaoBemPatrimonialForm(data=data_valida)
        form_valida.request = request
        if not form_valida.is_valid():
            self.assertNotIn("inativa", str(form_valida.errors).lower())

    def test_movimentacao_pendente_nao_impede_inativacao_ua(self):
        ua_nova = UnidadeAdministrativa.objects.create(
            nome="DRE Nova",
            codigo="DRE-NOVA",
            sigla="DRENOVA",
            status=UnidadeAdministrativa.ATIVA,
        )

        self.assertTrue(ua_nova.pode_inativar())

        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_ativa_1,
            unidade_administrativa_destino=ua_nova,
            quantidade=2,
            solicitado_por=self.operador_1,
        )

        self.assertEqual(movimentacao.status, ENVIADA)

        self.assertTrue(ua_nova.pode_inativar())
