from django.test import TestCase, RequestFactory
from django.contrib.auth.models import Group
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError

from usuario.models import Usuario
from usuario.admin import CustomUserModelAdmin
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from dados_comuns.models import UnidadeAdministrativa
from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.admins.bem_patrimonial import BemPatrimonialAdmin
from bem_patrimonial.constants import APROVADO


class GestorComUATestCase(TestCase):

    def setUp(self):
        self.ua1 = UnidadeAdministrativa.objects.create(
            codigo="001",
            nome="DRE Centro",
            sigla="DRC",
            status=UnidadeAdministrativa.ATIVA,
        )
        self.ua2 = UnidadeAdministrativa.objects.create(
            codigo="002",
            nome="DRE Sul",
            sigla="DRS",
            status=UnidadeAdministrativa.ATIVA,
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
        )
        self.gestor_sem_ua.groups.add(self.grupo_gestor)

        self.gestor_com_ua = Usuario.objects.create_user(
            username="gestor_com_ua",
            email="gestor_com_ua@test.com",
            password="test123",
            is_staff=True,
            unidade_administrativa=self.ua1,
        )
        self.gestor_com_ua.groups.add(self.grupo_gestor)

        self.operador = Usuario.objects.create_user(
            username="operador",
            email="operador@test.com",
            password="test123",
            is_staff=True,
            unidade_administrativa=self.ua2,
        )
        self.operador.groups.add(self.grupo_operador)

        self.bem_ua1 = BemPatrimonial.objects.create(
            nome="Bem UA1",
            descricao="Desc",
            valor_unitario=100.00,
            marca="Marca",
            modelo="Modelo",
            numero_processo="PROC-001",
            numero_patrimonial="000.000000001-0",
            status=APROVADO,
            unidade_administrativa=self.ua1,
            criado_por=self.gestor_com_ua,
        )

        self.bem_ua2 = BemPatrimonial.objects.create(
            nome="Bem UA2",
            descricao="Desc",
            valor_unitario=200.00,
            marca="Marca",
            modelo="Modelo",
            numero_processo="PROC-002",
            numero_patrimonial="000.000000002-0",
            status=APROVADO,
            unidade_administrativa=self.ua2,
            criado_por=self.operador,
        )

        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = BemPatrimonialAdmin(BemPatrimonial, self.site)

    def test_gestor_sem_ua_ve_todos_bens(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.gestor_sem_ua

        qs = self.admin.get_queryset(request)
        self.assertEqual(qs.count(), 2)
        self.assertIn(self.bem_ua1, qs)
        self.assertIn(self.bem_ua2, qs)

    def test_gestor_com_ua_ve_apenas_sua_ua(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.gestor_com_ua

        qs = self.admin.get_queryset(request)
        self.assertEqual(qs.count(), 1)
        self.assertIn(self.bem_ua1, qs)
        self.assertNotIn(self.bem_ua2, qs)

    def test_operador_ve_apenas_sua_ua(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.operador

        qs = self.admin.get_queryset(request)
        self.assertEqual(qs.count(), 1)
        self.assertIn(self.bem_ua2, qs)
        self.assertNotIn(self.bem_ua1, qs)

    def test_list_display_coluna_ua(self):
        request_gestor = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request_gestor.user = self.gestor_sem_ua
        self.assertIn(
            "unidade_administrativa", self.admin.get_list_display(request_gestor)
        )

        request_operador = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request_operador.user = self.operador
        self.assertNotIn(
            "unidade_administrativa", self.admin.get_list_display(request_operador)
        )

    def test_operador_sem_ua_nao_valida(self):
        admin_usuario = CustomUserModelAdmin(Usuario, self.site)
        form_class = admin_usuario.get_form(self.factory.get("/admin/"), obj=None)

        form = form_class(
            {
                "username": "novo_operador",
                "password1": "senha123",
                "password2": "senha123",
                "nome": "Novo Operador",
                "email": "novo@test.com",
                "is_staff": True,
                "groups": [self.grupo_operador.id],
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("unidade_administrativa", form.errors)

    def test_exportacao_respeita_regras_de_acesso(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")

        request.user = self.gestor_sem_ua
        self.assertEqual(self.admin.get_export_queryset(request).count(), 2)

        request.user = self.gestor_com_ua
        qs = self.admin.get_export_queryset(request)
        self.assertEqual(qs.count(), 1)
        self.assertIn(self.bem_ua1, qs)


class GestorMaisOperadorComUATestCase(TestCase):

    def setUp(self):
        self.ua1 = UnidadeAdministrativa.objects.create(
            codigo="001",
            nome="DRE Centro",
            sigla="DRC",
            status=UnidadeAdministrativa.ATIVA,
        )
        self.ua2 = UnidadeAdministrativa.objects.create(
            codigo="002",
            nome="DRE Sul",
            sigla="DRS",
            status=UnidadeAdministrativa.ATIVA,
        )

        self.grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        self.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

        self.gestor_operador = Usuario.objects.create_user(
            username="gestor_operador",
            email="gestor_operador@test.com",
            password="test123",
            is_staff=True,
            unidade_administrativa=self.ua1,
        )
        self.gestor_operador.groups.add(self.grupo_gestor, self.grupo_operador)

        self.bem_ua1 = BemPatrimonial.objects.create(
            nome="Bem UA1",
            descricao="Desc",
            valor_unitario=100.00,
            marca="Marca",
            modelo="Modelo",
            numero_processo="PROC-001",
            numero_patrimonial="000.000000001-0",
            status=APROVADO,
            unidade_administrativa=self.ua1,
            criado_por=self.gestor_operador,
        )

        self.bem_ua2 = BemPatrimonial.objects.create(
            nome="Bem UA2",
            descricao="Desc",
            valor_unitario=200.00,
            marca="Marca",
            modelo="Modelo",
            numero_processo="PROC-002",
            numero_patrimonial="000.000000002-0",
            status=APROVADO,
            unidade_administrativa=self.ua2,
            criado_por=self.gestor_operador,
        )

        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = BemPatrimonialAdmin(BemPatrimonial, self.site)

    def test_gestor_mais_operador_com_ua_ve_apenas_sua_ua(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.gestor_operador

        qs = self.admin.get_queryset(request)
        self.assertEqual(qs.count(), 1)
        self.assertIn(self.bem_ua1, qs)
        self.assertNotIn(self.bem_ua2, qs)
