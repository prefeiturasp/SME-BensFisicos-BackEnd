from django.test import TestCase, RequestFactory
from django.contrib.auth.models import Group
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError

from usuario.models import Usuario
from usuario.admin import CustomUserModelAdmin
from dados_comuns.models import UnidadeAdministrativa
from usuario.constants import GRUPO_OPERADOR_INVENTARIO, GRUPO_GESTOR_PATRIMONIO

from django.contrib.auth import get_user_model

User = get_user_model()


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


class UsuarioRFFieldTestCase(TestCase):

    def setUp(self):
        self.unidade = UnidadeAdministrativa.objects.create(
            codigo=100, nome="Unidade Teste", sigla="UT"
        )

    def test_usuario_can_be_created_with_valid_rf(self):
        usuario = Usuario.objects.create(
            username="user_rf_valid",
            nome="Usuario RF Valido",
            rf="123456",
            email="rfvalid@teste.com",
            unidade_administrativa=self.unidade,
        )
        self.assertEqual(usuario.rf, "123456")

    def test_usuario_can_be_created_without_rf(self):
        usuario = Usuario.objects.create(
            username="user_no_rf",
            nome="Usuario Sem RF",
            email="norf@teste.com",
            unidade_administrativa=self.unidade,
        )
        self.assertIsNone(usuario.rf)

    def test_rf_with_leading_zeros_is_preserved(self):
        usuario = Usuario.objects.create(
            username="user_rf_zeros",
            nome="Usuario RF Zeros",
            rf="001234",
            email="rfzeros@teste.com",
            unidade_administrativa=self.unidade,
        )
        self.assertEqual(usuario.rf, "001234")

    def test_rf_validation_rejects_letters(self):
        usuario = Usuario(
            username="user_rf_letters",
            nome="Usuario RF Letras",
            rf="ABC123",
            email="rfletters@teste.com",
            unidade_administrativa=self.unidade,
        )
        with self.assertRaises(ValidationError) as context:
            usuario.full_clean()

        self.assertIn("rf", context.exception.error_dict)
        self.assertIn("RF deve conter apenas números", str(context.exception))

    def test_rf_validation_rejects_special_characters(self):
        usuario = Usuario(
            username="user_rf_special",
            nome="Usuario RF Especial",
            rf="123-456",
            email="rfspecial@teste.com",
            unidade_administrativa=self.unidade,
        )
        with self.assertRaises(ValidationError) as context:
            usuario.full_clean()

        self.assertIn("rf", context.exception.error_dict)

    def test_rf_validation_rejects_spaces(self):
        usuario = Usuario(
            username="user_rf_spaces",
            nome="Usuario RF Espacos",
            rf="123 456",
            email="rfspaces@teste.com",
            unidade_administrativa=self.unidade,
        )
        with self.assertRaises(ValidationError) as context:
            usuario.full_clean()

        self.assertIn("rf", context.exception.error_dict)

    def test_rf_accepts_large_numbers(self):
        usuario = Usuario.objects.create(
            username="user_rf_large",
            nome="Usuario RF Grande",
            rf="9999999999999999",
            email="rflarge@teste.com",
            unidade_administrativa=self.unidade,
        )
        self.assertEqual(usuario.rf, "9999999999999999")


class CustomUserModelAdminReadonlyFieldsTestCase(TestCase):

    def setUp(self):
        self.site = AdminSite()
        self.admin = CustomUserModelAdmin(Usuario, self.site)
        self.factory = RequestFactory()

        self.unidade = UnidadeAdministrativa.objects.create(
            codigo=100, nome="Unidade Teste", sigla="UT"
        )

    def test_username_is_readonly_when_editing_existing_user(self):
        usuario = Usuario.objects.create(
            username="existing_user",
            nome="Usuario Existente",
            email="existing@teste.com",
            unidade_administrativa=self.unidade,
        )

        request = self.factory.get("/admin/usuario/usuario/")
        readonly_fields = self.admin.get_readonly_fields(request, obj=usuario)

        self.assertIn("username", readonly_fields)

    def test_username_is_not_readonly_when_creating_new_user(self):
        request = self.factory.get("/admin/usuario/usuario/add/")
        readonly_fields = self.admin.get_readonly_fields(request, obj=None)

        self.assertNotIn("username", readonly_fields)

    def test_get_readonly_fields_returns_tuple(self):
        usuario = Usuario.objects.create(
            username="user_tuple_test",
            nome="Usuario Tuple",
            email="tuple@teste.com",
            unidade_administrativa=self.unidade,
        )

        request = self.factory.get("/admin/usuario/usuario/")
        readonly_fields = self.admin.get_readonly_fields(request, obj=usuario)

        self.assertIsInstance(readonly_fields, tuple)


class CustomUserModelAdminFieldsetsTestCase(TestCase):

    def setUp(self):
        self.site = AdminSite()
        self.admin = CustomUserModelAdmin(Usuario, self.site)

    def test_rf_field_is_in_fieldsets(self):
        informacoes_pessoais_fields = None
        for fieldset in self.admin.fieldsets:
            if fieldset[0] == "Informações pessoais":
                informacoes_pessoais_fields = fieldset[1]["fields"]
                break

        self.assertIsNotNone(informacoes_pessoais_fields)
        self.assertIn("rf", informacoes_pessoais_fields)

    def test_rf_field_is_in_add_fieldsets(self):
        informacoes_pessoais_fields = None
        for fieldset in self.admin.add_fieldsets:
            if fieldset[0] == "Informações pessoais":
                informacoes_pessoais_fields = fieldset[1]["fields"]
                break

        self.assertIsNotNone(informacoes_pessoais_fields)
        self.assertIn("rf", informacoes_pessoais_fields)

    def test_rf_field_position_in_fieldsets(self):
        informacoes_pessoais_fields = None
        for fieldset in self.admin.fieldsets:
            if fieldset[0] == "Informações pessoais":
                informacoes_pessoais_fields = fieldset[1]["fields"]
                break

        self.assertIsNotNone(informacoes_pessoais_fields)
        fields_list = list(informacoes_pessoais_fields)
        nome_index = fields_list.index("nome")
        rf_index = fields_list.index("rf")

        self.assertEqual(
            rf_index, nome_index + 1, "RF deve estar logo após o campo nome"
        )

    def test_rf_field_position_in_add_fieldsets(self):
        informacoes_pessoais_fields = None
        for fieldset in self.admin.add_fieldsets:
            if fieldset[0] == "Informações pessoais":
                informacoes_pessoais_fields = fieldset[1]["fields"]
                break

        self.assertIsNotNone(informacoes_pessoais_fields)
        fields_list = list(informacoes_pessoais_fields)
        nome_index = fields_list.index("nome")
        rf_index = fields_list.index("rf")

        self.assertEqual(
            rf_index, nome_index + 1, "RF deve estar logo após o campo nome"
        )


class UsuarioModelTests(TestCase):
    def test_defaults_flags(self):
        u = User.objects.create_user(username="u1", password="x")
        self.assertTrue(
            u.must_change_password, "must_change_password deve iniciar como True"
        )
        self.assertIsNone(
            u.last_password_change, "last_password_change deve iniciar como None"
        )

    def test_can_update_last_password_change_and_flag(self):
        u = User.objects.create_user(username="u2", password="old")
        u.must_change_password = False
        u.save(update_fields=["must_change_password"])
        self.assertFalse(User.objects.get(pk=u.pk).must_change_password)
