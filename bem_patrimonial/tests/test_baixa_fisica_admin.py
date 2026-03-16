from dados_comuns.tests.auth_test_utils import auth_kwargs

from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.utils import timezone

from dados_comuns.tests.factories import criar_ua, criar_uo

from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO

from bem_patrimonial.models import (
    BaixaFisicaBemPatrimonial,
    BemPatrimonial,
    BaixaFisicaBensItem,
)

from bem_patrimonial.admins.baixa_fisica_bem_patrimonial import (
    BaixaFisicaBemPatrimonialAdmin,
)


class BaixaFisicaAdminTestCase(TestCase):

    def setUp(self):
        self.uo = criar_uo(codigo="100", nome="UO Teste", sigla="UOT")
        self.ua = criar_ua(
            uo=self.uo,
            codigo="001",
            nome="UA Teste",
            sigla="UAT",
        )

        self.grupo_gestor = Group.objects.get_or_create(
            name=GRUPO_GESTOR_PATRIMONIO
        )[0]

        self.user = Usuario.objects.create_user(
            username="gestor_baixa",
            email="gestor_baixa@test.com",
            **auth_kwargs("x"),
            is_staff=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )

        self.user.groups.add(self.grupo_gestor)

        self.factory = RequestFactory()
        self.site = AdminSite()

        self.admin = BaixaFisicaBemPatrimonialAdmin(
            BaixaFisicaBemPatrimonial,
            self.site,
        )

        self.bem = BemPatrimonial.objects.create(
            nome="Notebook Dell",
            descricao="Notebook para testes",
            valor_unitario=1000,
            marca="Dell",
            modelo="Latitude",
            numero_processo="PROC-TESTE",
            numero_patrimonial="000.000000010-0",
            unidade_administrativa=self.ua,
            criado_por=self.user,
        )

        self.baixa = BaixaFisicaBemPatrimonial.objects.create(
            numero_nbbpm="NBBPM-001",
            unidade_administrativa_origem=self.ua,
            criado_por=self.user,
        )

        BaixaFisicaBensItem.objects.create(
            baixa=self.baixa,
            bem=self.bem,
        )

    def _search(self, term):
        request = self.factory.get(
            "/admin/bem_patrimonial/baixafisicabempatrimonial/",
            {"q": term},
        )

        request.user = self.user

        qs = self.admin.get_queryset(request)

        qs, _ = self.admin.get_search_results(request, qs, term)

        return qs

    def test_busca_por_numero_nbbpm(self):
        qs = self._search("NBBPM-001")
        self.assertIn(self.baixa, qs)

    def test_busca_por_nome_bem(self):
        qs = self._search("Notebook Dell")
        self.assertIn(self.baixa, qs)

    def test_busca_por_numero_patrimonial(self):
        qs = self._search("000.000000010-0")
        self.assertIn(self.baixa, qs)

    def test_busca_por_unidade_administrativa(self):
        qs = self._search("UA Teste")
        self.assertIn(self.baixa, qs)

    def test_data_aprovacao_formatada_sem_data(self):
        resultado = self.admin.data_aprovacao_formatada(self.baixa)
        self.assertEqual(resultado, "-")

    def test_data_aprovacao_formatada_com_data(self):
        self.baixa.data_aprovacao = timezone.now()
        self.baixa.save()

        resultado = self.admin.data_aprovacao_formatada(self.baixa)

        self.assertNotEqual(resultado, "-")
        self.assertIsInstance(resultado, str)