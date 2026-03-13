from dados_comuns.tests.auth_test_utils import auth_kwargs
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from bem_patrimonial.admins.bem_patrimonial import BemPatrimonialAdmin
from bem_patrimonial.models import BemPatrimonial
from dados_comuns.tests.factories import criar_ua
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class BemPatrimonialAdminListDisplayTestCase(TestCase):

    EXPECTED_FIELDS = (
        "numero_patrimonial",
        "nome",
        "unidade_administrativa",
        "status",
    )

    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = BemPatrimonialAdmin(BemPatrimonial, self.site)
        self.unidade = criar_ua(codigo="UA001", nome="Unidade Teste", sigla="DRE")

        from django.contrib.auth.models import Group

        self.gestor = Usuario.objects.create_user(
            username="gestor",
            email="gestor@teste.com",
            **auth_kwargs("senha123"),
            unidade_administrativa=self.unidade,
            unidade_orcamentaria=self.unidade.unidade_orcamentaria,
        )
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.gestor.groups.add(grupo_gestor)

        self.operador = Usuario.objects.create_user(
            username="operador",
            email="operador@teste.com",
            **auth_kwargs("senha123"),
            unidade_administrativa=self.unidade,
            unidade_orcamentaria=self.unidade.unidade_orcamentaria,
        )
        grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
        self.operador.groups.add(grupo_operador)
        self.operador.unidades_administrativas.add(self.unidade)

    def _make_request(self, user):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = user
        return request

    def test_list_display_gestor_and_operador_are_equal(self):
        gestor_fields = self.admin.get_list_display(self._make_request(self.gestor))
        operador_fields = self.admin.get_list_display(self._make_request(self.operador))
        self.assertEqual(gestor_fields, operador_fields)

    def test_list_display_contains_required_fields(self):
        actual = self.admin.get_list_display(self._make_request(self.gestor))
        self.assertEqual(actual, self.EXPECTED_FIELDS)

    def test_list_display_has_four_fields(self):
        actual = self.admin.get_list_display(self._make_request(self.gestor))
        self.assertEqual(len(actual), 4)

    def test_list_display_shows_unidade_administrativa(self):
        actual = self.admin.get_list_display(self._make_request(self.operador))
        self.assertIn("unidade_administrativa", actual)

    def test_list_display_does_not_contain_old_fields(self):
        old_fields = ["id", "descricao", "criado_por", "criado_em"]
        for user in (self.gestor, self.operador):
            actual = self.admin.get_list_display(self._make_request(user))
            for field in old_fields:
                self.assertNotIn(field, actual)

    def _is_valid_list_display_entry(self, name: str) -> bool:
        model_fields = {f.name for f in BemPatrimonial._meta.get_fields()}
        if name in model_fields:
            return True
        if hasattr(self.admin, name):
            return True
        if hasattr(BemPatrimonial, name):
            return True
        return False

    def test_list_display_fields_are_valid(self):
        actual = self.admin.get_list_display(self._make_request(self.gestor))
        for field in actual:
            self.assertTrue(
                self._is_valid_list_display_entry(field),
                f"O campo '{field}' não existe como campo do modelo nem como método válido para list_display.",
            )
