from dados_comuns.tests.auth_test_utils import auth_kwargs
from django.test import TestCase, RequestFactory
from django.contrib import admin
from django.contrib.auth import get_user_model

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.admins.bem_patrimonial import BemPatrimonialAdmin
from dados_comuns.tests.factories import criar_ua, criar_uo


class BemPatrimonialAdminTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_superuser(
            username="admin", email="admin@example.com", **auth_kwargs("admin123")
        )
        self.uo = criar_uo(codigo="100", nome="UO 100")

        self.ua = criar_ua(nome="UA Teste", unidade_orcamentaria=self.uo)
        self.admin_user.unidade_administrativa = self.ua
        self.admin_user.save()

        self.factory = RequestFactory()
        self.model_admin = BemPatrimonialAdmin(BemPatrimonial, admin.site)

    def _mk_bem(self, **kwargs):
        data = {
            "nome": "Item Teste",
            "descricao": "Desc",
            "valor_unitario": 1.00,
            "marca": "M",
            "modelo": "X",
            "numero_processo": "PROC-1",
            "numero_patrimonial": "000.000000001-0",
            "numero_formato_antigo": False,
            "sem_numeracao": False,
            "criado_por": self.admin_user,
        }
        data.update(kwargs)
        return BemPatrimonial.objects.create(**data)

    def _get_form_for(self, obj=None):
        if obj:
            request = self.factory.get(
                f"/admin/bem_patrimonial/bempatrimonial/{obj.pk}/change/"
            )
        else:
            request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/add/")
        request.user = self.admin_user
        return self.model_admin.get_form(request, obj=obj)

    def test_criacao_flags_habilitadas_e_numero_editavel(self):
        form_cls = self._get_form_for(None)
        form = form_cls()

        self.assertIn("numero_patrimonial", form.fields)
        self.assertIn("sem_numeracao", form.fields)
        self.assertIn("numero_formato_antigo", form.fields)

        self.assertFalse(getattr(form.fields["sem_numeracao"], "disabled", False))
        self.assertFalse(
            getattr(form.fields["numero_formato_antigo"], "disabled", False)
        )
        self.assertFalse(getattr(form.fields["numero_patrimonial"], "disabled", False))

    def test_edicao_trava_flags_mas_numero_editavel_quando_nao_sem_numeracao(self):

        obj = self._mk_bem(numero_patrimonial="000.000000123-4", sem_numeracao=False)
        form_cls = self._get_form_for(obj)
        form = form_cls(instance=obj)

        self.assertTrue(getattr(form.fields["sem_numeracao"], "disabled", False))
        if "numero_formato_antigo" in form.fields:
            self.assertFalse(form.fields["numero_formato_antigo"].disabled)
        self.assertFalse(getattr(form.fields["numero_patrimonial"], "disabled", False))
