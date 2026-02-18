from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.admins.bem_patrimonial import BemPatrimonialAdmin
from bem_patrimonial.constants import APROVADO
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.admin import UnidadeAdministrativaAdmin
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class UnidadeAdministrativaAutocompleteTestCase(TestCase):

    def setUp(self):

        self.ua1_ativa = criar_ua(
            codigo="001",
            nome="DRE Centro",
            sigla="DRC",
            status=UnidadeAdministrativa.ATIVA,
        )
        self.ua2_ativa = criar_ua(
            uo=self.ua1_ativa.unidade_orcamentaria,
            codigo="002",
            nome="DRE Sul",
            sigla="DRS",
            status=UnidadeAdministrativa.ATIVA,
        )
        self.ua3_inativa = criar_ua(
            uo=self.ua1_ativa.unidade_orcamentaria,
            codigo="003",
            nome="DRE Norte",
            sigla="DRN",
            status=UnidadeAdministrativa.INATIVA,
        )

        self.grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        self.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

        self.gestor_sem_ua = Usuario.objects.create_user(
            username="gestor_sem_ua",
            email="gestor_sem_ua@test.com",
            password="test123",
            is_staff=True,
            unidade_orcamentaria=self.ua1_ativa.unidade_orcamentaria,
        )
        self.gestor_sem_ua.groups.add(self.grupo_gestor)

        self.operador_com_ua1 = Usuario.objects.create_user(
            username="operador_ua1",
            email="operador_ua1@test.com",
            password="test123",
            is_staff=True,
            unidade_administrativa=self.ua1_ativa,
            unidade_orcamentaria=self.ua1_ativa.unidade_orcamentaria,
        )
        self.operador_com_ua1.groups.add(self.grupo_operador)

        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = UnidadeAdministrativaAdmin(UnidadeAdministrativa, self.site)

    def test_autocomplete_ua_origem_filtra_por_usuario(self):
        request_operador = self.factory.get(
            "/admin/autocomplete/",
            {"field_name": "unidade_administrativa_origem", "term": ""},
        )
        request_operador.user = self.operador_com_ua1
        qs_operador, _ = self.admin.get_search_results(
            request_operador, UnidadeAdministrativa.objects.all(), ""
        )
        self.assertEqual(qs_operador.count(), 1)
        self.assertIn(self.ua1_ativa, qs_operador)

        request_gestor = self.factory.get(
            "/admin/autocomplete/",
            {"field_name": "unidade_administrativa_origem", "term": ""},
        )
        request_gestor.user = self.gestor_sem_ua
        qs_gestor, _ = self.admin.get_search_results(
            request_gestor, UnidadeAdministrativa.objects.all(), ""
        )
        self.assertEqual(qs_gestor.count(), 2)
        self.assertNotIn(self.ua3_inativa, qs_gestor)
