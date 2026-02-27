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
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class MovimentacaoQuerysetAcessoTestCase(TestCase):

    def setUp(self):
        self.ua1 = criar_ua(codigo="001", nome="DRE Centro", sigla="DRC")
        self.ua2 = criar_ua(
            uo=self.ua1.unidade_orcamentaria,
            codigo="002",
            nome="DRE Sul",
            sigla="DRS",
            status=UnidadeAdministrativa.ATIVA,
        )
        self.ua3 = criar_ua(
            uo=self.ua1.unidade_orcamentaria,
            codigo="003",
            nome="DRE Norte",
            sigla="DRN",
            status=UnidadeAdministrativa.ATIVA,
        )

        self.grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        self.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

        self.gestor_sem_ua = Usuario.objects.create_user(
            username="gestor_sem_ua",
            email="gestor_sem_ua@test.com",
            password="test123",
            is_staff=True,
            unidade_orcamentaria=self.ua1.unidade_orcamentaria,
        )
        self.gestor_sem_ua.groups.add(self.grupo_gestor)

        self.gestor_com_ua1 = Usuario.objects.create_user(
            username="gestor_com_ua1",
            email="gestor_com_ua1@test.com",
            password="test123",
            is_staff=True,
            unidade_administrativa=self.ua1,
            unidade_orcamentaria=self.ua1.unidade_orcamentaria,
        )
        self.gestor_com_ua1.groups.add(self.grupo_gestor)

        self.operador_ua1 = Usuario.objects.create_user(
            username="operador_ua1",
            email="operador_ua1@test.com",
            password="test123",
            is_staff=True,
            unidade_administrativa=self.ua1,
            unidade_orcamentaria=self.ua1.unidade_orcamentaria,
        )
        self.operador_ua1.groups.add(self.grupo_operador)
        self.operador_ua1.unidades_administrativas.add(self.ua1)

        self.operador_ua2 = Usuario.objects.create_user(
            username="operador_ua2",
            email="operador_ua2@test.com",
            password="test123",
            is_staff=True,
            unidade_administrativa=self.ua2,
            unidade_orcamentaria=self.ua2.unidade_orcamentaria,
        )
        self.operador_ua2.groups.add(self.grupo_operador)
        self.operador_ua2.unidades_administrativas.add(self.ua2)

        self.bem_ua1 = BemPatrimonial.objects.create(
            nome="Bem UA1",
            descricao="Desc",
            valor_unitario=100.00,
            marca="Marca",
            modelo="Modelo",
            numero_processo="PROC-001",
            numero_patrimonial="000.000000001-0",
            status=APROVADO,
            unidade_administrativa=self.ua1,
            criado_por=self.operador_ua1,
        )

        self.bem_ua2 = BemPatrimonial.objects.create(
            nome="Bem UA2",
            descricao="Desc",
            valor_unitario=200.00,
            marca="Marca",
            modelo="Modelo",
            numero_processo="PROC-002",
            numero_patrimonial="000.000000002-0",
            status=APROVADO,
            unidade_administrativa=self.ua2,
            criado_por=self.operador_ua2,
        )

        self.bem_ua3 = BemPatrimonial.objects.create(
            nome="Bem UA3",
            descricao="Desc",
            valor_unitario=300.00,
            marca="Marca",
            modelo="Modelo",
            numero_processo="PROC-003",
            numero_patrimonial="000.000000003-0",
            status=APROVADO,
            unidade_administrativa=self.ua3,
            criado_por=self.gestor_sem_ua,
        )

        self.mov1 = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua1,
            unidade_administrativa_destino=self.ua2,
            solicitado_por=self.operador_ua1,
        )
        MovimentacaoBensItem.objects.create(movimentacao=self.mov1, bem=self.bem_ua1)

        self.mov2 = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua2,
            unidade_administrativa_destino=self.ua3,
            solicitado_por=self.operador_ua2,
        )
        MovimentacaoBensItem.objects.create(movimentacao=self.mov2, bem=self.bem_ua2)

        self.mov3 = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua3,
            unidade_administrativa_destino=self.ua1,
            solicitado_por=self.gestor_sem_ua,
        )
        MovimentacaoBensItem.objects.create(movimentacao=self.mov3, bem=self.bem_ua3)

        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = MovimentacaoBemPatrimonialAdmin(
            MovimentacaoBemPatrimonial, self.site
        )

    def test_gestor_sem_ua_ve_todas_movimentacoes(self):
        request = self.factory.get("/admin/bem_patrimonial/movimentacaobempatrimonial/")
        request.user = self.gestor_sem_ua

        qs = self.admin.get_queryset(request)
        self.assertEqual(qs.count(), 3)
        self.assertIn(self.mov1, qs)
        self.assertIn(self.mov2, qs)
        self.assertIn(self.mov3, qs)

    def test_gestor_com_ua_ve_movimentacoes_origem_ou_destino(self):
        request = self.factory.get("/admin/bem_patrimonial/movimentacaobempatrimonial/")
        request.user = self.gestor_com_ua1

        qs = self.admin.get_queryset(request)
        self.assertEqual(qs.count(), 2)
        self.assertIn(self.mov1, qs)
        self.assertNotIn(self.mov2, qs)
        self.assertIn(self.mov3, qs)

    def test_operador_com_ua_ve_movimentacoes_origem_ou_destino(self):
        request = self.factory.get("/admin/bem_patrimonial/movimentacaobempatrimonial/")
        request.user = self.operador_ua2

        qs = self.admin.get_queryset(request)
        self.assertEqual(qs.count(), 2)
        self.assertIn(self.mov1, qs)
        self.assertIn(self.mov2, qs)
        self.assertNotIn(self.mov3, qs)
