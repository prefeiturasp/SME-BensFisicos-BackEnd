from django.test import TestCase
from django.contrib.admin.sites import AdminSite
from bem_patrimonial.admins.bem_patrimonial import BemPatrimonialAdmin
from bem_patrimonial.models import BemPatrimonial


class BemPatrimonialAdminListDisplayTestCase(TestCase):

    def setUp(self):
        self.site = AdminSite()
        self.admin = BemPatrimonialAdmin(BemPatrimonial, self.site)

    def test_list_display_contains_required_fields(self):
        expected_fields = (
            "numero_patrimonial",
            "nome",
            "unidade_administrativa",
            "status",
        )
        self.assertEqual(self.admin.list_display, expected_fields)

    def test_list_display_does_not_contain_old_fields(self):
        old_fields = ["id", "descricao", "criado_por", "criado_em"]
        for field in old_fields:
            self.assertNotIn(field, self.admin.list_display)

    def test_list_display_fields_are_valid(self):
        model_fields = [f.name for f in BemPatrimonial._meta.get_fields()]

        for field in self.admin.list_display:
            self.assertIn(
                field,
                model_fields,
                f"O campo '{field}' não existe no modelo BemPatrimonial",
            )
