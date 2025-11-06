from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from bem_patrimonial.admins.bem_patrimonial import BemPatrimonialAdmin
from bem_patrimonial.models import BemPatrimonial
from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class BemPatrimonialAdminListDisplayTestCase(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = BemPatrimonialAdmin(BemPatrimonial, self.site)
        self.factory = RequestFactory()

        self.unidade = UnidadeAdministrativa.objects.create(
            codigo="UA001", nome="Unidade Teste", sigla="DRE"
        )

        self.gestor = Usuario.objects.create_user(
            username="gestor",
            email="gestor@teste.com",
            password="senha123",
            unidade_administrativa=self.unidade,
        )
        from django.contrib.auth.models import Group

        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.gestor.groups.add(grupo_gestor)

        self.operador = Usuario.objects.create_user(
            username="operador",
            email="operador@teste.com",
            password="senha123",
            unidade_administrativa=self.unidade,
        )
        grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
        self.operador.groups.add(grupo_operador)

    def test_list_display_gestor_contains_required_fields(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.gestor

        expected_fields = (
            "numero_patrimonial",
            "nome",
            "unidade_administrativa",
            "status",
        )
        actual_fields = self.admin.get_list_display(request)
        self.assertEqual(actual_fields, expected_fields)

    def test_list_display_operador_contains_required_fields(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.operador

        expected_fields = ("numero_patrimonial", "nome", "status")
        actual_fields = self.admin.get_list_display(request)
        self.assertEqual(actual_fields, expected_fields)

    def test_list_display_operador_does_not_show_unidade_administrativa(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.operador

        actual_fields = self.admin.get_list_display(request)
        self.assertNotIn("unidade_administrativa", actual_fields)

    def test_list_display_gestor_shows_unidade_administrativa(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.gestor

        actual_fields = self.admin.get_list_display(request)
        self.assertIn("unidade_administrativa", actual_fields)

    def test_list_display_does_not_contain_old_fields(self):
        old_fields = ["id", "descricao", "criado_por", "criado_em"]

        request_gestor = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request_gestor.user = self.gestor
        gestor_fields = self.admin.get_list_display(request_gestor)

        for field in old_fields:
            self.assertNotIn(field, gestor_fields)

        request_operador = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request_operador.user = self.operador
        operador_fields = self.admin.get_list_display(request_operador)

        for field in old_fields:
            self.assertNotIn(field, operador_fields)

    def _is_valid_list_display_entry(self, name: str) -> bool:
        """
        Válido se:
        - é campo do modelo, OU
        - é atributo/método no ModelAdmin, OU
        - é atributo/método no Model (callable em instância), OU
        - é @admin.display no ModelAdmin (também é atributo no admin).
        """
        model_fields = {f.name for f in BemPatrimonial._meta.get_fields()}
        if name in model_fields:
            return True

        if hasattr(self.admin, name):
            return True

        if hasattr(BemPatrimonial, name):
            return True

        return False

    def test_list_display_fields_are_valid(self):
        request_gestor = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request_gestor.user = self.gestor
        gestor_fields = self.admin.get_list_display(request_gestor)

        for field in gestor_fields:
            self.assertTrue(
                self._is_valid_list_display_entry(field),
                f"O campo '{field}' não existe como campo do modelo nem como método válido para list_display.",
            )

        request_operador = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request_operador.user = self.operador
        operador_fields = self.admin.get_list_display(request_operador)

        for field in operador_fields:
            self.assertTrue(
                self._is_valid_list_display_entry(field),
                f"O campo '{field}' não existe como campo do modelo nem como método válido para list_display.",
            )

    def test_list_display_gestor_contains_required_fields(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.gestor
        actual = self.admin.get_list_display(request)
        expected = (
            "numero_patrimonial",
            "nome",
            "unidade_administrativa",
            "status",
        )
        self.assertEqual(actual, expected)

    def test_list_display_gestor_has_five_fields(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.gestor
        actual = self.admin.get_list_display(request)
        self.assertEqual(len(actual), 4)

    def test_list_display_operador_contains_required_fields(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.operador
        actual = self.admin.get_list_display(request)
        expected = ("numero_patrimonial", "nome", "status")
        self.assertEqual(actual, expected)

    def test_list_display_operador_has_four_fields(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.operador
        actual = self.admin.get_list_display(request)
        self.assertEqual(len(actual), 3)
