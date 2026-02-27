from django.test import TestCase, RequestFactory
from django.contrib.auth.models import Group
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from unittest.mock import patch
from types import SimpleNamespace

from dados_comuns.tests.factories import criar_ua, criar_uo
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria
from usuario.models import Usuario
from usuario.admin import CustomUserModelAdmin
from usuario.constants import GRUPO_OPERADOR_INVENTARIO, GRUPO_GESTOR_PATRIMONIO

from django.contrib.auth import get_user_model

User = get_user_model()


class SetupData:

    def create_instance(self):
        uo = criar_uo()
        ua = criar_ua(uo=uo)

        obj = {
            "username": "usuario",
            "password": "@@User20201",
            "nome": "Veronica Silva",
            "email": "usuario@gmail.com",
            "unidade_orcamentaria": uo,  # ✅ novo
            "unidade_administrativa": ua,  # ✅ usar a UA criada
            "is_staff": True,
        }
        usuario = Usuario.objects.create(**obj)
        self.add_group(usuario)
        usuario.unidades_administrativas.add(ua)

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

        self.unidade1 = criar_ua(
            codigo=200,
            sigla="UB",
            nome="Unidade B",
        )
        self.unidade2 = criar_ua(
            uo=self.unidade1.unidade_orcamentaria,
            codigo=100,
            nome="Unidade A",
            sigla="UA",
        )
        self.unidade3 = criar_ua(
            uo=self.unidade1.unidade_orcamentaria,
            codigo=150,
            nome="Unidade C",
            sigla="UC",
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
            unidade_administrativa=self.unidade1,
            unidade_orcamentaria=self.unidade1.unidade_orcamentaria,
        )
        usuario2 = Usuario.objects.create(
            username="user2",
            nome="Usuario 2",
            email="user2@teste.com",
            unidade_administrativa=self.unidade2,
            unidade_orcamentaria=self.unidade2.unidade_orcamentaria,
        )
        usuario3 = Usuario.objects.create(
            username="user3",
            nome="Usuario 3",
            email="user3@teste.com",
            unidade_administrativa=self.unidade3,
            unidade_orcamentaria=self.unidade3.unidade_orcamentaria,
        )

        request = self.factory.get("/admin/usuario/usuario/")
        queryset = self.admin.get_queryset(request)

        usuarios_ordenados = list(queryset)
        self.assertEqual(usuarios_ordenados[0].id, usuario2.id)
        self.assertEqual(usuarios_ordenados[1].id, usuario3.id)
        self.assertEqual(usuarios_ordenados[2].id, usuario1.id)

    def test_get_grupo_returns_gestor_patrimonio(self):
        usuario = Usuario.objects.create(
            username="gestor",
            nome="Gestor Teste",
            email="gestor@teste.com",
            unidade_administrativa=self.unidade1,
            unidade_orcamentaria=self.unidade1.unidade_orcamentaria,
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
            unidade_orcamentaria=self.unidade1.unidade_orcamentaria,
        )
        usuario.groups.add(self.group_operador)
        usuario.unidades_administrativas.add(self.unidade1)

        result = self.admin.get_grupo(usuario)
        self.assertEqual(result, "OPERADOR_INVENTARIO")

    def test_get_grupo_returns_dash_when_no_group(self):
        usuario = Usuario.objects.create(
            username="semgrupo",
            nome="Sem Grupo",
            email="semgrupo@teste.com",
            unidade_administrativa=self.unidade1,
            unidade_orcamentaria=self.unidade1.unidade_orcamentaria,
        )

        result = self.admin.get_grupo(usuario)
        self.assertEqual(result, "-")

    def test_get_grupo_prioritizes_gestor_when_both_groups(self):
        usuario = Usuario.objects.create(
            username="ambos",
            nome="Ambos Grupos",
            email="ambos@teste.com",
            unidade_administrativa=self.unidade1,
            unidade_orcamentaria=self.unidade1.unidade_orcamentaria,
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
        self.unidade = criar_ua()

    def test_usuario_can_be_created_with_valid_rf(self):
        usuario = Usuario.objects.create(
            username="user_rf_valid",
            nome="Usuario RF Valido",
            rf="123456",
            email="rfvalid@teste.com",
            unidade_administrativa=self.unidade,
            unidade_orcamentaria=self.unidade.unidade_orcamentaria,
        )
        self.assertEqual(usuario.rf, "123456")

    def test_usuario_can_be_created_without_rf(self):
        usuario = Usuario.objects.create(
            username="user_no_rf",
            nome="Usuario Sem RF",
            email="norf@teste.com",
            unidade_administrativa=self.unidade,
            unidade_orcamentaria=self.unidade.unidade_orcamentaria,
        )
        self.assertIsNone(usuario.rf)

    def test_rf_with_leading_zeros_is_preserved(self):
        usuario = Usuario.objects.create(
            username="user_rf_zeros",
            nome="Usuario RF Zeros",
            rf="F001234",
            email="rfzeros@teste.com",
            unidade_administrativa=self.unidade,
            unidade_orcamentaria=self.unidade.unidade_orcamentaria,
        )
        self.assertEqual(usuario.rf, "F001234")

    def test_rf_validation_rejects_invalid_pattern(self):
        usuario = Usuario(
            username="user_rf_invalid",
            nome="Usuario RF Invalido",
            rf="FG093393",  # duas letras → inválido
            email="rfinvalid@teste.com",
            unidade_administrativa=self.unidade,
            unidade_orcamentaria=self.unidade.unidade_orcamentaria,
        )
        usuario.set_password("Senha@123")

        with self.assertRaises(ValidationError) as context:
            usuario.full_clean()

        self.assertIn("rf", context.exception.error_dict)
        self.assertIn(
            "RF deve começar com uma letra e conter apenas números após ela. Ex: F53399 ou f53399.",
            str(context.exception),
        )

    def test_rf_validation_accepts_valid_pattern(self):
        usuario = Usuario(
            username="user_rf_valid",
            nome="Usuario RF Valido",
            rf="B098890",
            email="rfvalido@teste.com",
            unidade_administrativa=self.unidade,
            unidade_orcamentaria=self.unidade.unidade_orcamentaria,
        )
        usuario.set_password("Senha@123")

        usuario.full_clean()

    def test_rf_validation_rejects_special_characters(self):
        usuario = Usuario(
            username="user_rf_special",
            nome="Usuario RF Especial",
            rf="F123-456",
            email="rfspecial@teste.com",
            unidade_administrativa=self.unidade,
            unidade_orcamentaria=self.unidade.unidade_orcamentaria,
        )
        with self.assertRaises(ValidationError) as context:
            usuario.full_clean()

        self.assertIn("rf", context.exception.error_dict)

    def test_rf_validation_rejects_spaces(self):
        usuario = Usuario(
            username="user_rf_spaces",
            nome="Usuario RF Espacos",
            rf="F123 456",
            email="rfspaces@teste.com",
            unidade_administrativa=self.unidade,
            unidade_orcamentaria=self.unidade.unidade_orcamentaria,
        )
        with self.assertRaises(ValidationError) as context:
            usuario.full_clean()

        self.assertIn("rf", context.exception.error_dict)

    def test_rf_accepts_large_numbers(self):
        usuario = Usuario.objects.create(
            username="user_rf_large",
            nome="Usuario RF Grande",
            rf="F9999999999999999",
            email="rflarge@teste.com",
            unidade_administrativa=self.unidade,
            unidade_orcamentaria=self.unidade.unidade_orcamentaria,
        )
        self.assertEqual(usuario.rf, "F9999999999999999")


class CustomUserModelAdminReadonlyFieldsTestCase(TestCase):

    def setUp(self):
        self.site = AdminSite()
        self.admin = CustomUserModelAdmin(Usuario, self.site)
        self.factory = RequestFactory()

        self.unidade = criar_ua()

    def test_username_is_readonly_when_editing_existing_user(self):
        usuario = Usuario.objects.create(
            username="existing_user",
            nome="Usuario Existente",
            email="existing@teste.com",
            unidade_administrativa=self.unidade,
            unidade_orcamentaria=self.unidade.unidade_orcamentaria,
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
            unidade_orcamentaria=self.unidade.unidade_orcamentaria,
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


class CustomUserModelAdminManyToManyQuerysetTestCase(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.admin = CustomUserModelAdmin(Usuario, self.site)
        self.factory = RequestFactory()

        self.ua_uo1_a = criar_ua(codigo="101", sigla="U1A", nome="UA UO1 A")
        self.ua_uo1_b = criar_ua(
            uo=self.ua_uo1_a.unidade_orcamentaria,
            codigo="102",
            sigla="U1B",
            nome="UA UO1 B",
        )
        self.uo2 = criar_uo(codigo="UO-999", sigla="UO2", nome="UO 2")
        self.ua_uo2 = criar_ua(
            uo=self.uo2,
            codigo="201",
            sigla="U2A",
            nome="UA UO2",
        )

        self.admin_user = Usuario.objects.create_user(
            username="admin_uo1",
            password="senha123",
            is_staff=True,
            unidade_orcamentaria=self.ua_uo1_a.unidade_orcamentaria,
            must_change_password=False,
        )

        self.superuser = Usuario.objects.create_superuser(
            username="super_admin_uo",
            email="super@teste.com",
            password="senha123",
            must_change_password=False,
        )

    def test_m2m_queryset_no_add_usa_uo_do_usuario_logado(self):
        request = self.factory.get("/admin/usuario/usuario/add/")
        request.user = self.admin_user

        field = Usuario._meta.get_field("unidades_administrativas")
        formfield = self.admin.formfield_for_manytomany(field, request)

        qs_ids = set(formfield.queryset.values_list("id", flat=True))

        self.assertIn(self.ua_uo1_a.id, qs_ids)
        self.assertIn(self.ua_uo1_b.id, qs_ids)
        self.assertNotIn(self.ua_uo2.id, qs_ids)

    def test_fk_queryset_no_add_usa_uo_do_usuario_logado(self):
        request = self.factory.get("/admin/usuario/usuario/add/")
        request.user = self.admin_user

        field = Usuario._meta.get_field("unidade_administrativa")
        formfield = self.admin.formfield_for_foreignkey(field, request)

        qs_ids = set(formfield.queryset.values_list("id", flat=True))

        self.assertIn(self.ua_uo1_a.id, qs_ids)
        self.assertIn(self.ua_uo1_b.id, qs_ids)
        self.assertNotIn(self.ua_uo2.id, qs_ids)

    def test_superuser_add_sem_uo_param_usa_primeira_uo_no_fk_e_m2m(self):
        request = self.factory.get("/admin/usuario/usuario/add/")
        request.user = self.superuser

        expected_first_uo_id = (
            UnidadeAdministrativa.objects.filter(status=UnidadeAdministrativa.ATIVA)
            .order_by("unidade_orcamentaria__codigo", "codigo", "id")
            .values_list("unidade_orcamentaria_id", flat=True)
            .first()
        )
        if not expected_first_uo_id:
            expected_first_uo = UnidadeOrcamentaria.objects.order_by(
                "codigo", "id"
            ).first()
            self.assertIsNotNone(expected_first_uo)
            expected_first_uo_id = expected_first_uo.id

        fk_field = Usuario._meta.get_field("unidade_administrativa")
        fk_formfield = self.admin.formfield_for_foreignkey(fk_field, request)
        fk_uo_ids = set(
            fk_formfield.queryset.values_list("unidade_orcamentaria_id", flat=True)
        )

        m2m_field = Usuario._meta.get_field("unidades_administrativas")
        m2m_formfield = self.admin.formfield_for_manytomany(m2m_field, request)
        m2m_uo_ids = set(
            m2m_formfield.queryset.values_list("unidade_orcamentaria_id", flat=True)
        )

        self.assertEqual(fk_uo_ids, {expected_first_uo_id})
        self.assertEqual(m2m_uo_ids, {expected_first_uo_id})

    def test_grupo_single_select_nao_dispara_erro_lista(self):
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)

        request = self.factory.post(
            "/admin/usuario/usuario/add/",
            data={
                "unidade_orcamentaria": str(self.ua_uo1_a.unidade_orcamentaria_id),
                "groups": str(grupo_gestor.id),
            },
        )
        request.user = self.superuser

        form_class = self.admin.get_form(request, obj=None)
        form = form_class(
            data={
                "username": "usuario_select_unico",
                "password1": "Teste@12345!x",
                "password2": "Teste@12345!x",
                "nome": "Usuario Select",
                "email": "select@teste.com",
                "is_staff": True,
                "unidade_orcamentaria": str(self.ua_uo1_a.unidade_orcamentaria_id),
                "unidade_administrativa": str(self.ua_uo1_a.id),
                "unidades_administrativas": [str(self.ua_uo1_a.id)],
                "groups": str(grupo_gestor.id),
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_grupo_single_select_exibe_opcao_vazia(self):
        request = self.factory.get("/admin/usuario/usuario/add/")
        request.user = self.superuser

        form_class = self.admin.get_form(request, obj=None)
        form = form_class()
        html = form["groups"].as_widget()
        self.assertIn('<option value="" selected>---------</option>', html)

    def test_grupo_single_select_renderiza_opcao_vazia_no_html(self):
        """Garante que o HTML do widget renderiza a opção vazia (mesmo cenário do exibe_opcao_vazia)."""
        self.test_grupo_single_select_exibe_opcao_vazia()

    def test_change_form_usuario_com_grupo_inicia_com_grupo_atual(self):
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        usuario = Usuario.objects.create_user(
            username="usuario_com_grupo_initial",
            password="senha123",
            unidade_orcamentaria=self.ua_uo1_a.unidade_orcamentaria,
            unidade_administrativa=self.ua_uo1_a,
            is_staff=True,
            must_change_password=False,
        )
        usuario.groups.set([grupo_gestor])

        request = self.factory.get(f"/admin/usuario/usuario/{usuario.pk}/change/")
        request.user = self.superuser

        form_class = self.admin.get_form(request, obj=usuario)
        form = form_class(instance=usuario)

        valor = form["groups"].value()
        self.assertTrue(valor)
        self.assertIn(str(grupo_gestor.pk), [str(v) for v in valor])

    def test_save_related_nao_limpa_grupo_se_groups_nao_veio_no_post(self):
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        usuario = Usuario.objects.create_user(
            username="usuario_sem_groups_post",
            password="senha123",
            unidade_orcamentaria=self.ua_uo1_a.unidade_orcamentaria,
            unidade_administrativa=self.ua_uo1_a,
            is_staff=True,
            must_change_password=False,
        )
        usuario.groups.set([grupo_gestor])

        request = self.factory.post(
            f"/admin/usuario/usuario/{usuario.pk}/change/",
            data={"nome": "Sem groups no post"},
        )
        request.user = self.superuser
        form = SimpleNamespace(instance=usuario, cleaned_data={})

        with patch(
            "django.contrib.auth.admin.UserAdmin.save_related", return_value=None
        ):
            self.admin.save_related(request, form, [], change=True)

        usuario.refresh_from_db()
        self.assertTrue(usuario.groups.filter(name=GRUPO_GESTOR_PATRIMONIO).exists())

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
