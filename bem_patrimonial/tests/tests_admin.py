from django.test import TestCase, RequestFactory
from django.contrib import admin
from django.contrib.auth import get_user_model

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.admins.bem_patrimonial import BemPatrimonialAdmin
from bem_patrimonial.constants import ORIGENS
from dados_comuns.models import UnidadeAdministrativa


class BemPatrimonialAdminTest(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="admin123"
        )

        self.ua = UnidadeAdministrativa.objects.create(nome="UA Teste")
        self.admin_user.unidade_administrativa = self.ua
        self.admin_user.save()

        self.factory = RequestFactory()
        self.model_admin = BemPatrimonialAdmin(BemPatrimonial, admin.site)

        self.origem = ORIGENS[0][0]

    def _mk_bem(self, **kwargs):
        data = dict(
            nome="Item Teste",
            descricao="Desc",
            quantidade=1,
            valor_unitario=1,
            marca="M",
            modelo="X",
            data_compra_entrega="2025-10-10",
            origem=self.origem,
            numero_processo=1,
            numero_patrimonial="000.000000001-0",
            numero_formato_antigo=False,
            sem_numeracao=False,
            criado_por=self.admin_user,
        )
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

    def test_edicao_trava_flags_e_trava_numero_quando_criado_com_sem_numeracao(self):

        obj = self._mk_bem(numero_patrimonial=None, sem_numeracao=True)
        form_cls = self._get_form_for(obj)
        form = form_cls()

        self.assertTrue(getattr(form.fields["sem_numeracao"], "disabled", False))
        self.assertTrue(
            getattr(form.fields["numero_formato_antigo"], "disabled", False)
        )
        self.assertTrue(getattr(form.fields["numero_patrimonial"], "disabled", False))

    def test_edicao_trava_flags_mas_numero_editavel_quando_nao_sem_numeracao(self):

        obj = self._mk_bem(numero_patrimonial="000.000000123-4", sem_numeracao=False)
        form_cls = self._get_form_for(obj)
        form = form_cls()

        self.assertTrue(getattr(form.fields["sem_numeracao"], "disabled", False))
        self.assertTrue(
            getattr(form.fields["numero_formato_antigo"], "disabled", False)
        )
        self.assertFalse(getattr(form.fields["numero_patrimonial"], "disabled", False))
