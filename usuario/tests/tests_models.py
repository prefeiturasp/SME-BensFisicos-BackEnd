from django.test import TestCase, RequestFactory
from django.contrib.auth.models import Group
from django.contrib.admin.sites import AdminSite

from usuario.models import Usuario
from usuario.admin import CustomUserModelAdmin
from dados_comuns.models import UnidadeAdministrativa
from usuario.constants import GRUPO_OPERADOR_INVENTARIO, GRUPO_GESTOR_PATRIMONIO


class SetupData:
    def create_unidade(self):
        UnidadeAdministrativa.objects.create(codigo=123, nome="COTIC", sigla="COTIC")

    def create_instance(self):
        self.create_unidade()

        obj = {
            "username": "usuario",
            "password": "@@User20201",
            "nome": "Veronica Silva",
            "email": "usuario@gmail.com",
            "unidade_administrativa": UnidadeAdministrativa.objects.first(),
            "is_staff": True,
        }
        usuario = Usuario.objects.create(**obj)
        self.add_group(usuario)

        return usuario

    def add_group(self, usuario):
        group_operador_inventario, _ = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )
        usuario.groups.add(group_operador_inventario)


class UsuarioTestCase(TestCase):
    start = SetupData()
    entity = Usuario

    def setUp(self):
        self.start.create_instance()

    def test_get(self):
        instance = self.entity.objects.first()
        self.assertIsInstance(instance, self.entity)

    def test_delete(self):
        instance = self.entity.objects.first()
        instance.delete()

        self.assertFalse(instance.id)
        self.assertIsInstance(instance, self.entity)


class CustomUserModelAdminTestCase(TestCase):

    def setUp(self):
        self.site = AdminSite()
        self.admin = CustomUserModelAdmin(Usuario, self.site)
        self.factory = RequestFactory()

        self.unidade1 = UnidadeAdministrativa.objects.create(
            codigo=200, nome="Unidade B", sigla="UB"
        )
        self.unidade2 = UnidadeAdministrativa.objects.create(
            codigo=100, nome="Unidade A", sigla="UA"
        )
        self.unidade3 = UnidadeAdministrativa.objects.create(
            codigo=150, nome="Unidade C", sigla="UC"
        )

        self.group_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        self.group_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

    def test_list_display_contains_correct_fields(self):
        expected_fields = ("nome", "email", "unidade_administrativa", "get_grupo")
        self.assertEqual(self.admin.list_display, expected_fields)

    def test_list_display_does_not_contain_id(self):
        self.assertNotIn("id", self.admin.list_display)

    def test_list_display_does_not_contain_date_joined(self):
        self.assertNotIn("date_joined", self.admin.list_display)

    def test_ordering_by_unidade_administrativa_codigo(self):
        self.assertEqual(self.admin.ordering, ("unidade_administrativa__codigo",))

    def test_queryset_is_ordered_by_unidade_codigo(self):
        usuario1 = Usuario.objects.create(
            username="user1",
            nome="Usuario 1",
            email="user1@teste.com",
            unidade_administrativa=self.unidade1,  # codigo=200
        )
        usuario2 = Usuario.objects.create(
            username="user2",
            nome="Usuario 2",
            email="user2@teste.com",
            unidade_administrativa=self.unidade2,  # codigo=100
        )
        usuario3 = Usuario.objects.create(
            username="user3",
            nome="Usuario 3",
            email="user3@teste.com",
            unidade_administrativa=self.unidade3,  # codigo=150
        )

        request = self.factory.get("/admin/usuario/usuario/")
        queryset = self.admin.get_queryset(request)

        usuarios_ordenados = list(queryset)
        self.assertEqual(usuarios_ordenados[0].id, usuario2.id)  # codigo=100
        self.assertEqual(usuarios_ordenados[1].id, usuario3.id)  # codigo=150
        self.assertEqual(usuarios_ordenados[2].id, usuario1.id)  # codigo=200

    def test_get_grupo_returns_gestor_patrimonio(self):
        usuario = Usuario.objects.create(
            username="gestor",
            nome="Gestor Teste",
            email="gestor@teste.com",
            unidade_administrativa=self.unidade1,
        )
        usuario.groups.add(self.group_gestor)

        result = self.admin.get_grupo(usuario)
        self.assertEqual(result, "GESTOR_PATRIMONIO")

    def test_get_grupo_returns_operador_inventario(self):
        usuario = Usuario.objects.create(
            username="operador",
            nome="Operador Teste",
            email="operador@teste.com",
            unidade_administrativa=self.unidade1,
        )
        usuario.groups.add(self.group_operador)

        result = self.admin.get_grupo(usuario)
        self.assertEqual(result, "OPERADOR_INVENTARIO")

    def test_get_grupo_returns_dash_when_no_group(self):
        usuario = Usuario.objects.create(
            username="semgrupo",
            nome="Sem Grupo",
            email="semgrupo@teste.com",
            unidade_administrativa=self.unidade1,
        )

        result = self.admin.get_grupo(usuario)
        self.assertEqual(result, "-")

    def test_get_grupo_prioritizes_gestor_when_both_groups(self):
        usuario = Usuario.objects.create(
            username="ambos",
            nome="Ambos Grupos",
            email="ambos@teste.com",
            unidade_administrativa=self.unidade1,
        )
        usuario.groups.add(self.group_gestor)
        usuario.groups.add(self.group_operador)

        result = self.admin.get_grupo(usuario)
        self.assertEqual(result, "GESTOR_PATRIMONIO")

    def test_get_grupo_has_correct_display_description(self):
        self.assertEqual(self.admin.get_grupo.short_description, "Grupo")

    def test_nome_is_first_field_in_list_display(self):
        self.assertEqual(self.admin.list_display[0], "nome")
