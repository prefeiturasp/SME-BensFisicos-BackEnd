from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib import messages
from django.contrib.auth.models import Group

from bem_patrimonial.models import BemPatrimonial, StatusBemPatrimonial
from bem_patrimonial.constants import (
    AGUARDANDO_APROVACAO,
    APROVADO,
    NAO_APROVADO,
)
from bem_patrimonial.admins.bem_patrimonial import (
    BemPatrimonialAdmin,
    aprovar_bens,
    reprovar_bens,
)
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class BaseAprovacaoTestCase(TestCase):

    def setUp(self):
        self.grupo_gestor = Group.objects.create(name=GRUPO_GESTOR_PATRIMONIO)
        self.grupo_operador = Group.objects.create(name=GRUPO_OPERADOR_INVENTARIO)
        self.uo = criar_uo(codigo="100", nome="UO 100")
        self.ua = criar_ua(
            nome="UA Teste",
            codigo="001",
            sigla="UAT",
            status=UnidadeAdministrativa.ATIVA,
        )

        self.gestor = Usuario.objects.create_user(
            username="gestor",
            email="gestor@test.com",
            password="senha123",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.ua.unidade_orcamentaria,
        )
        self.gestor.groups.add(self.grupo_gestor)

        self.operador = Usuario.objects.create_user(
            username="operador",
            email="operador@test.com",
            password="senha123",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.ua.unidade_orcamentaria,
        )
        self.operador.groups.add(self.grupo_operador)
        self.operador.unidades_administrativas.add(self.ua)

        self.factory = RequestFactory()
        self.admin = BemPatrimonialAdmin(BemPatrimonial, AdminSite())


class AprovacaoLoteTestCase(BaseAprovacaoTestCase):
    def setUp(self):
        super().setUp()

        self.bem1 = BemPatrimonial.objects.create(
            nome="Bem 1",
            descricao="Descrição 1",
            valor_unitario=100.00,
            marca="Marca 1",
            modelo="Modelo 1",
            numero_processo="PROC-001",
            sem_numeracao=True,
            criado_por=self.operador,
            unidade_administrativa=self.ua,
            status=AGUARDANDO_APROVACAO,
        )

        self.bem2 = BemPatrimonial.objects.create(
            nome="Bem 2",
            descricao="Descrição 2",
            valor_unitario=200.00,
            marca="Marca 2",
            modelo="Modelo 2",
            numero_processo="PROC-002",
            sem_numeracao=True,
            criado_por=self.operador,
            unidade_administrativa=self.ua,
            status=AGUARDANDO_APROVACAO,
        )

        self.bem_aprovado = BemPatrimonial.objects.create(
            nome="Bem Aprovado",
            descricao="Já aprovado",
            valor_unitario=300.00,
            marca="Marca 3",
            modelo="Modelo 3",
            numero_processo="PROC-003",
            sem_numeracao=True,
            criado_por=self.operador,
            unidade_administrativa=self.ua,
            status=APROVADO,
        )

    def _create_request_with_messages(self, user):
        request = self.factory.post("/admin/")
        request.user = user
        setattr(request, "session", "session")
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    def test_gestor_pode_aprovar_bens_em_lote(self):
        queryset = BemPatrimonial.objects.filter(pk__in=[self.bem1.pk, self.bem2.pk])
        request = self._create_request_with_messages(self.gestor)

        aprovar_bens(self.admin, request, queryset)

        self.bem1.refresh_from_db()
        self.bem2.refresh_from_db()

        self.assertEqual(self.bem1.status, APROVADO)
        self.assertEqual(self.bem2.status, APROVADO)

       

    def test_gestor_pode_reprovar_bens_em_lote(self):
        queryset = BemPatrimonial.objects.filter(pk__in=[self.bem1.pk, self.bem2.pk])
        request = self._create_request_with_messages(self.gestor)

        reprovar_bens(self.admin, request, queryset)

        self.bem1.refresh_from_db()
        self.bem2.refresh_from_db()

        self.assertEqual(self.bem1.status, NAO_APROVADO)
        self.assertEqual(self.bem2.status, NAO_APROVADO)



    def test_operador_nao_pode_aprovar_bens(self):
        queryset = BemPatrimonial.objects.filter(pk__in=[self.bem1.pk, self.bem2.pk])
        request = self._create_request_with_messages(self.operador)

        aprovar_bens(self.admin, request, queryset)

        self.bem1.refresh_from_db()
        self.bem2.refresh_from_db()

        self.assertEqual(self.bem1.status, AGUARDANDO_APROVACAO)
        self.assertEqual(self.bem2.status, AGUARDANDO_APROVACAO)

        msgs = [str(m) for m in messages.get_messages(request)]
        self.assertTrue(any("permissão" in msg.lower() for msg in msgs))

    def test_operador_nao_pode_reprovar_bens(self):
        queryset = BemPatrimonial.objects.filter(pk__in=[self.bem1.pk, self.bem2.pk])
        request = self._create_request_with_messages(self.operador)

        reprovar_bens(self.admin, request, queryset)

        self.bem1.refresh_from_db()
        self.bem2.refresh_from_db()

        self.assertEqual(self.bem1.status, AGUARDANDO_APROVACAO)
        self.assertEqual(self.bem2.status, AGUARDANDO_APROVACAO)

        msgs = [str(m) for m in messages.get_messages(request)]
        self.assertTrue(any("permissão" in msg.lower() for msg in msgs))

    def test_nao_aprova_bens_ja_aprovados(self):
        queryset = BemPatrimonial.objects.filter(
            pk__in=[self.bem1.pk, self.bem_aprovado.pk]
        )
        request = self._create_request_with_messages(self.gestor)

        aprovar_bens(self.admin, request, queryset)

        self.bem1.refresh_from_db()
        self.bem_aprovado.refresh_from_db()

        self.assertEqual(self.bem1.status, APROVADO)
        self.assertEqual(self.bem_aprovado.status, APROVADO)

        msgs = [str(m) for m in messages.get_messages(request)]
        self.assertTrue(any("1 bem(ns) aprovado(s)" in msg for msg in msgs))
        self.assertTrue(
            any(
                "não estava(m) com status 'Aguardando aprovação'" in msg for msg in msgs
            )
        )

    def test_nao_reprova_bens_ja_aprovados(self):
        queryset = BemPatrimonial.objects.filter(
            pk__in=[self.bem1.pk, self.bem_aprovado.pk]
        )
        request = self._create_request_with_messages(self.gestor)

        reprovar_bens(self.admin, request, queryset)

        self.bem1.refresh_from_db()
        self.bem_aprovado.refresh_from_db()

        self.assertEqual(self.bem1.status, NAO_APROVADO)
        self.assertEqual(self.bem_aprovado.status, APROVADO)

        msgs = [str(m) for m in messages.get_messages(request)]
        self.assertTrue(any("1 bem(ns) reprovado(s)" in msg for msg in msgs))
        self.assertTrue(
            any(
                "não estava(m) com status 'Aguardando aprovação'" in msg for msg in msgs
            )
        )

    def test_mensagem_quando_nenhum_bem_aguardando_aprovacao(self):
        queryset = BemPatrimonial.objects.filter(pk=self.bem_aprovado.pk)
        request = self._create_request_with_messages(self.gestor)

        aprovar_bens(self.admin, request, queryset)

        msgs = [str(m) for m in messages.get_messages(request)]
        self.assertTrue(
            any(
                "Nenhum bem selecionado está com status 'Aguardando aprovação'" in msg
                for msg in msgs
            )
        )

    def test_actions_nao_disponiveis_para_operador(self):
        request = self._create_request_with_messages(self.operador)
        actions = self.admin.get_actions(request)

        self.assertNotIn("aprovar_bens", actions)
        self.assertNotIn("reprovar_bens", actions)

    def test_actions_disponiveis_para_gestor(self):
        request = self._create_request_with_messages(self.gestor)
        actions = self.admin.get_actions(request)

        self.assertIn("aprovar_bens", actions)
        self.assertIn("reprovar_bens", actions)


class FormularioStatusTestCase(BaseAprovacaoTestCase):

    def test_campo_status_nao_aparece_no_formulario_edicao(self):
        bem = BemPatrimonial.objects.create(
            nome="Bem Teste",
            descricao="Descrição Teste",
            valor_unitario=100.00,
            marca="Marca Teste",
            modelo="Modelo Teste",
            numero_processo="PROC-001",
            sem_numeracao=True,
            criado_por=self.operador,
            unidade_administrativa=self.ua,
            status=AGUARDANDO_APROVACAO,
        )

        request = self.factory.get(
            f"/admin/bem_patrimonial/bempatrimonial/{bem.pk}/change/"
        )
        request.user = self.gestor

        form_class = self.admin.get_form(request, obj=bem)
        form = form_class(instance=bem)

        self.assertNotIn("status", form.fields)


class InlineStatusTestCase(BaseAprovacaoTestCase):

    def setUp(self):
        super().setUp()

        self.bem = BemPatrimonial.objects.create(
            nome="Bem Teste",
            descricao="Descrição Teste",
            valor_unitario=100.00,
            marca="Marca Teste",
            modelo="Modelo Teste",
            numero_processo="PROC-001",
            sem_numeracao=True,
            criado_por=self.gestor,
            unidade_administrativa=self.ua,
            status=AGUARDANDO_APROVACAO,
        )

    def test_apenas_historico_geral_inline_esta_presente(self):
        from bem_patrimonial.admins.bem_patrimonial import (
            HistoricoGeralInline,
            StatusBemPatrimonialInline,
        )

        inline_classes = list(self.admin.inlines)

        self.assertEqual(len(inline_classes), 1)

        self.assertEqual(inline_classes[0], HistoricoGeralInline)

        inline_class_types = [inline.__class__ for inline in self.admin.inlines]
        self.assertNotIn(StatusBemPatrimonialInline, inline_class_types)
