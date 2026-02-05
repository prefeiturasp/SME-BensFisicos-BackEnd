from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group

from bem_patrimonial.models import (
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
    MovimentacaoBensItem,
)
from bem_patrimonial.admins.movimentacao_bem_patrimonial import (
    MovimentacaoBemPatrimonialAdmin,
)
from bem_patrimonial.constants import APROVADO
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class MovimentacaoAdminSearchTestCase(TestCase):

    def setUp(self):
        self.uo_a = criar_uo(codigo="UO-100", nome="UO Alfa", sigla="UOA")
        self.uo_b = criar_uo(codigo="UO-200", nome="UO Beta", sigla="UOB")

        self.ua1 = criar_ua(uo=self.uo_a, codigo="001", nome="DRE Centro", sigla="DRC")
        self.ua2 = criar_ua(uo=self.uo_a, codigo="002", nome="DRE Sul", sigla="DRS")
        self.ua3 = criar_ua(uo=self.uo_b, codigo="003", nome="DRE Norte", sigla="DRN")
        self.ua4 = criar_ua(uo=self.uo_b, codigo="004", nome="DRE Leste", sigla="DRL")

        self.grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        self.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

        self.gestor_uo_a = Usuario.objects.create_user(
            username="gestor_uo_a",
            email="gestor_uo_a@test.com",
            password="test123",
            is_staff=True,
            unidade_orcamentaria=self.uo_a,
        )
        self.gestor_uo_a.groups.add(self.grupo_gestor)

        self.gestor_uo_b = Usuario.objects.create_user(
            username="gestor_uo_b",
            email="gestor_uo_b@test.com",
            password="test123",
            is_staff=True,
            unidade_orcamentaria=self.uo_b,
        )
        self.gestor_uo_b.groups.add(self.grupo_gestor)

        self.operador_ua2 = Usuario.objects.create_user(
            username="operador_ua2",
            email="operador_ua2@test.com",
            password="test123",
            is_staff=True,
            unidade_administrativa=self.ua2,
            unidade_orcamentaria=self.uo_a,
        )
        self.operador_ua2.groups.add(self.grupo_operador)

        self.bem_ua1 = BemPatrimonial.objects.create(
            nome="Bem UA1",
            descricao="Descricao A",
            valor_unitario=100.00,
            marca="Marca A",
            modelo="Modelo A",
            numero_processo="PROC-001",
            numero_patrimonial="000.000000001-0",
            localizacao="Sala 101",
            status=APROVADO,
            unidade_administrativa=self.ua1,
            criado_por=self.gestor_uo_a,
        )

        self.bem_ua2 = BemPatrimonial.objects.create(
            nome="Bem UA2",
            descricao="Descricao B",
            valor_unitario=200.00,
            marca="Marca B",
            modelo="Modelo B",
            numero_processo="PROC-002",
            numero_patrimonial="000.000000002-0",
            localizacao="Sala 202",
            status=APROVADO,
            unidade_administrativa=self.ua2,
            criado_por=self.operador_ua2,
        )

        self.bem_ua3 = BemPatrimonial.objects.create(
            nome="Bem UA3",
            descricao="Descricao C",
            valor_unitario=300.00,
            marca="Marca C",
            modelo="Modelo C",
            numero_processo="PROC-003",
            numero_patrimonial="000.000000003-0",
            localizacao="Sala 303",
            status=APROVADO,
            unidade_administrativa=self.ua3,
            criado_por=self.gestor_uo_b,
        )

        self.mov1 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem_ua1,
            unidade_administrativa_origem=self.ua1,
            unidade_administrativa_destino=self.ua2,
            solicitado_por=self.gestor_uo_a,
            numero_cimbpm="CIMBPM-001",
        )
        MovimentacaoBensItem.objects.create(movimentacao=self.mov1, bem=self.bem_ua1)

        self.mov2 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem_ua2,
            unidade_administrativa_origem=self.ua2,
            unidade_administrativa_destino=self.ua1,
            solicitado_por=self.operador_ua2,
            numero_cimbpm="CIMBPM-002",
        )
        MovimentacaoBensItem.objects.create(movimentacao=self.mov2, bem=self.bem_ua2)

        self.mov3 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem_ua3,
            unidade_administrativa_origem=self.ua3,
            unidade_administrativa_destino=self.ua4,
            solicitado_por=self.gestor_uo_b,
            numero_cimbpm="CIMBPM-003",
        )
        MovimentacaoBensItem.objects.create(movimentacao=self.mov3, bem=self.bem_ua3)

        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = MovimentacaoBemPatrimonialAdmin(
            MovimentacaoBemPatrimonial, self.site
        )

    def _search(self, user, term):
        request = self.factory.get(
            "/admin/bem_patrimonial/movimentacaobempatrimonial/", {"q": term}
        )
        request.user = user
        qs = self.admin.get_queryset(request)
        qs, _ = self.admin.get_search_results(request, qs, term)
        return qs

    def _assert_search_contains(self, user, term, expected, not_expected=None):
        qs = self._search(user, term)
        self.assertIn(expected, qs)
        if not_expected is not None:
            self.assertNotIn(not_expected, qs)

    def test_busca_por_campos_do_bem(self):
        casos = [
            ("000.000000001-0", self.mov1),
            ("Bem UA1", self.mov1),
            ("Descricao A", self.mov1),
            ("Marca A", self.mov1),
            ("Modelo A", self.mov1),
            ("Sala 101", self.mov1),
            ("PROC-001", self.mov1),
            ("000.000000002-0", self.mov2),
            ("Bem UA2", self.mov2),
            ("Descricao B", self.mov2),
            ("Marca B", self.mov2),
            ("Modelo B", self.mov2),
            ("Sala 202", self.mov2),
            ("PROC-002", self.mov2),
        ]

        for termo, mov in casos:
            with self.subTest(termo=termo):
                self._assert_search_contains(self.gestor_uo_a, termo, mov, self.mov3)

    def test_busca_por_numero_cimbpm(self):
        self._assert_search_contains(
            self.gestor_uo_a, "CIMBPM-002", self.mov2, self.mov1
        )

    def test_busca_por_ua_origem_destino(self):
        qs = self._search(self.gestor_uo_a, "DRE Centro")
        self.assertIn(self.mov1, qs)
        self.assertIn(self.mov2, qs)
        self.assertNotIn(self.mov3, qs)

        qs = self._search(self.gestor_uo_a, "002")
        self.assertIn(self.mov1, qs)
        self.assertIn(self.mov2, qs)
        self.assertNotIn(self.mov3, qs)

    def test_busca_por_unidade_orcamentaria(self):
        self._assert_search_contains(self.gestor_uo_b, "UO-200", self.mov3, self.mov1)
        self._assert_search_contains(self.gestor_uo_b, "UO Beta", self.mov3, self.mov1)

    def test_busca_respeita_escopo_operador(self):
        qs = self._search(self.operador_ua2, "PROC-003")
        self.assertNotIn(self.mov3, qs)
