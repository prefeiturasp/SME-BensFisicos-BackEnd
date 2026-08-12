from dados_comuns.tests.auth_test_utils import auth_kwargs
from django.test import TestCase, RequestFactory
from django.contrib import admin
from django.contrib.auth import get_user_model

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.admins.bem_patrimonial import BemPatrimonialAdmin
from bem_patrimonial.admins.filters.baixados_periodo_filter import (
    StatusBemPatrimonialFilter,
)
from bem_patrimonial import constants
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


class StatusBemPatrimonialFilterTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username="admin_status_filter",
            email="admin.status.filter@test.com",
            **auth_kwargs("123456"),
        )
        self.ua = criar_ua(uo=criar_uo(codigo="910", nome="UO 910"))
        self.model_admin = BemPatrimonialAdmin(BemPatrimonial, admin.site)
        self.bem_aprovado = self._criar_bem("Bem aprovado", constants.APROVADO)
        self.bem_transferido = self._criar_bem(
            "Bem transferido", constants.TRANSFERIDO
        )

    def _criar_bem(self, nome, status):
        return BemPatrimonial.objects.create(
            nome=nome,
            descricao="Descricao",
            valor_unitario=1,
            marca="Marca",
            modelo="Modelo",
            numero_processo="PROC-1",
            numero_patrimonial=f"000.00000000{BemPatrimonial.objects.count() + 1}-0",
            numero_formato_antigo=False,
            sem_numeracao=False,
            criado_por=self.user,
            unidade_administrativa=self.ua,
            status=status,
        )

    def _filtro(self, data=None):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/", data)
        request.user = self.user
        return StatusBemPatrimonialFilter(
            request,
            request.GET.copy(),
            BemPatrimonial,
            self.model_admin,
        ), request

    def test_padrao_exibe_todos_sem_transferidos(self):
        filtro, request = self._filtro()

        queryset = filtro.queryset(request, BemPatrimonial.objects.all())

        self.assertEqual(list(queryset), [self.bem_aprovado])

    def test_status_transferido_exibe_apenas_transferidos(self):
        filtro, request = self._filtro(
            {StatusBemPatrimonialFilter.parameter_name: constants.TRANSFERIDO}
        )

        queryset = filtro.queryset(request, BemPatrimonial.objects.all())

        self.assertEqual(list(queryset), [self.bem_transferido])

    def test_opcao_padrao_comunica_que_transferidos_nao_sao_exibidos(self):
        filtro, _ = self._filtro()

        class ChangeListFake:
            def get_query_string(self, *args, **kwargs):
                return "?"

        choices = list(filtro.choices(ChangeListFake()))

        self.assertEqual(choices[0]["display"], "Todos (sem transferidos)")
        self.assertTrue(choices[0]["selected"])
