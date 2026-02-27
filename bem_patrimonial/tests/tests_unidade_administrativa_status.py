from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib import messages

from bem_patrimonial.models import (
    MovimentacaoBemPatrimonial,
    MovimentacaoBensItem,
)
from bem_patrimonial.constants import ENVIADA, ACEITA
from bem_patrimonial.admins.movimentacao_bem_patrimonial import (
    MovimentacaoBemPatrimonialAdmin,
    aprovar_solicitacao,
)
from bem_patrimonial.admins.forms.movimentacao_bem_patrimonial_form import (
    MovimentacaoBemPatrimonialForm,
)
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua
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
        self.bem = setup.create_bem_patrimonial(self.operador_1, self.ua_ativa_1)

        self.factory = RequestFactory()

    def _create_form_with_request(self, user, data):
        request = self.factory.post("/admin/")
        request.user = user
        form = MovimentacaoBemPatrimonialForm(data=data)
        form.request = request
        return form

    def test_nao_pode_criar_movimentacao_com_ua_origem_inativa(self):
        data = {
            "unidade_administrativa_origem": self.ua_inativa.pk,
            "unidade_administrativa_destino": self.ua_ativa_2.pk,
        }

        form = self._create_form_with_request(self.gestor, data)
        self.assertFalse(form.is_valid())
        errors = str(form.errors).lower()

        self.assertIn("faça uma escolha válida", errors)
        self.assertIn("unidade administrativa de origem é obrigatória", errors)

    def test_nao_pode_criar_movimentacao_com_ua_destino_inativa(self):
        data = {
            "unidade_administrativa_origem": self.ua_ativa_1.pk,
            "unidade_administrativa_destino": self.ua_inativa.pk,
        }

        form = self._create_form_with_request(self.operador_1, data)
        self.assertFalse(form.is_valid())

        errors = str(form.errors).lower()
        self.assertIn("faça uma escolha válida", errors)
        self.assertIn("unidade administrativa de destino", errors)

    def test_nao_pode_criar_movimentacao_com_ambas_uas_inativas(self):
        ua_inativa_2 = criar_ua(
            nome="DRE Leste Inativa",
            codigo="DRE-LESTE",
            sigla="DREL",
            status=UnidadeAdministrativa.INATIVA,
            uo=self.ua_inativa.unidade_orcamentaria,
        )

        data = {
            "unidade_administrativa_origem": self.ua_inativa.pk,
            "unidade_administrativa_destino": ua_inativa_2.pk,
        }

        form = self._create_form_with_request(self.gestor, data)
        self.assertFalse(form.is_valid())

        self.assertIn(
            "faça uma escolha válida. sua escolha não é uma das disponíveis",
            str(form.errors).lower(),
        )

    def test_pode_criar_movimentacao_com_ambas_uas_ativas(self):
        data = {
            "unidade_administrativa_origem": self.ua_ativa_1.pk,
            "unidade_administrativa_destino": self.ua_ativa_2.pk,
        }

        form = self._create_form_with_request(self.operador_1, data)
        self.assertTrue(form.is_valid())


class AprovacaoRejeicaoMovimentacaoComUAInativaTestCase(TestCase):

    def setUp(self):
        setup = SetupUnidadeAdministrativaStatusData()
        self.ua_origem, self.ua_destino, self.ua_inativa = (
            setup.create_unidades_administrativas()
        )
        self.operador_origem, self.operador_destino, self.gestor = (
            setup.create_usuarios(self.ua_origem, self.ua_destino)
        )
        self.bem = setup.create_bem_patrimonial(self.operador_origem, self.ua_origem)

        self.movimentacao = MovimentacaoBemPatrimonial.objects.create(
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

    def test_nao_pode_aprovar_se_ua_origem_inativada(self):
        self.ua_origem.status = UnidadeAdministrativa.INATIVA
        self.ua_origem.save()

        request = self._create_request_with_messages(self.operador_destino)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)
        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ENVIADA)

        msgs = [str(m).lower() for m in messages.get_messages(request)]
        self.assertTrue(any("origem" in m and "inativa" in m for m in msgs))

    def test_nao_pode_aprovar_se_ua_destino_inativada(self):
        self.ua_destino.status = UnidadeAdministrativa.INATIVA
        self.ua_destino.save()

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)
        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ENVIADA)

        msgs = [str(m).lower() for m in messages.get_messages(request)]
        self.assertTrue(any("destino" in m and "inativa" in m for m in msgs))

    def test_pode_aprovar_se_ambas_uas_ativas(self):
        MovimentacaoBensItem.objects.create(
            movimentacao=self.movimentacao,
            bem=self.bem,
        )

        request = self._create_request_with_messages(self.operador_destino)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ACEITA)


class InativacaoUAComBensTestCase(TestCase):

    def setUp(self):
        setup = SetupUnidadeAdministrativaStatusData()
        self.ua_ativa_1, self.ua_ativa_2, self.ua_inativa = (
            setup.create_unidades_administrativas()
        )
        self.operador_1, self.operador_2, self.gestor = setup.create_usuarios(
            self.ua_ativa_1, self.ua_ativa_2
        )
        self.bem = setup.create_bem_patrimonial(self.operador_1, self.ua_ativa_1)

    def test_nao_pode_inativar_ua_com_bens(self):
        self.assertFalse(self.ua_ativa_1.pode_inativar())

    def test_pode_inativar_ua_sem_bens(self):
        nova = criar_ua(
            nome="DRE Teste",
            codigo="DRE-TESTE",
            sigla="DRET",
            status=UnidadeAdministrativa.ATIVA,
            uo=self.ua_ativa_1.unidade_orcamentaria,
        )
        self.assertTrue(nova.pode_inativar())

    def test_pode_inativar_movendo_bens_para_outra_ua(self):
        self.bem.set_unidade_administrative(self.ua_ativa_2)
        self.assertTrue(self.ua_ativa_1.pode_inativar())


class AutocompleteComUAInativaTestCase(TestCase):
    def setUp(self):
        setup = SetupUnidadeAdministrativaStatusData()
        self.ua_ativa_1, self.ua_ativa_2, self.ua_inativa = (
            setup.create_unidades_administrativas()
        )
        self.operador_1, self.operador_2, self.gestor = setup.create_usuarios(
            self.ua_ativa_1, self.ua_ativa_2
        )
        self.bem = setup.create_bem_patrimonial(self.operador_1, self.ua_ativa_1)

    def test_form_filtra_uas_ativas_origem(self):
        form = MovimentacaoBemPatrimonialForm()
        qs = form.fields["unidade_administrativa_origem"].queryset
        self.assertIn(self.ua_ativa_1, qs)
        self.assertNotIn(self.ua_inativa, qs)

    def test_form_filtra_uas_ativas_destino(self):
        form = MovimentacaoBemPatrimonialForm()
        qs = form.fields["unidade_administrativa_destino"].queryset
        self.assertIn(self.ua_ativa_1, qs)
        self.assertNotIn(self.ua_inativa, qs)
