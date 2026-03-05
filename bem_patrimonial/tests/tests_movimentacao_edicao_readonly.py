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
from bem_patrimonial.admins.forms.movimentacao_bem_patrimonial_form import (
    MovimentacaoBemPatrimonialForm,
)
from bem_patrimonial.constants import APROVADO
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class MovimentacaoEdicaoReadonlyTestCase(TestCase):

    def setUp(self):
        self.ua1 = criar_ua(
            codigo="001",
            nome="DRE Centro",
            sigla="DRC",
            status=UnidadeAdministrativa.ATIVA,
        )
        self.ua2 = criar_ua(
            uo=self.ua1.unidade_orcamentaria,
            codigo="002",
            nome="DRE Sul",
            sigla="DRS",
            status=UnidadeAdministrativa.ATIVA,
        )

        self.grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        self.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

        self.gestor = Usuario.objects.create_user(
            username="gestor",
            email="gestor@test.com",
            password="test123",
            is_staff=True,
            unidade_orcamentaria=self.ua1.unidade_orcamentaria,
        )
        self.gestor.groups.add(self.grupo_gestor)

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

        self.bem = BemPatrimonial.objects.create(
            nome="Bem Teste",
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

        self.movimentacao = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua1,
            unidade_administrativa_destino=self.ua2,
            solicitado_por=self.operador_ua1,
            observacao="Observação inicial",
        )
        self.item = MovimentacaoBensItem.objects.create(
            movimentacao=self.movimentacao,
            bem=self.bem,
        )

        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = MovimentacaoBemPatrimonialAdmin(
            MovimentacaoBemPatrimonial, self.site
        )

    def test_uas_readonly_na_edicao_nao_na_criacao(self):
        request = self.factory.get("/admin/bem_patrimonial/movimentacaobempatrimonial/")
        request.user = self.gestor

        readonly_edicao = self.admin.get_readonly_fields(request, obj=self.movimentacao)
        self.assertIn("unidade_administrativa_origem", readonly_edicao)
        self.assertIn("unidade_administrativa_destino", readonly_edicao)

        readonly_criacao = self.admin.get_readonly_fields(request, obj=None)
        self.assertEqual(len(readonly_criacao), 0)

    def test_validacao_uas_so_acontece_na_criacao(self):
        form_criacao = MovimentacaoBemPatrimonialForm(
            data={
                "unidade_administrativa_origem": self.ua1.pk,
                "unidade_administrativa_destino": self.ua1.pk,  # Mesma UA - inválido
                "observacao": "Teste",
            }
        )
        form_criacao.request = type("obj", (object,), {"user": self.gestor})()

        self.assertFalse(form_criacao.is_valid())
        self.assertIn(
            "Operação não permitida: origem e destino são iguais",
            str(form_criacao.errors),
        )

        form_edicao = MovimentacaoBemPatrimonialForm(
            data={
                "unidade_administrativa_origem": self.ua1.pk,
                "unidade_administrativa_destino": self.ua1.pk,
                "observacao": "Observação atualizada",
            },
            instance=self.movimentacao,
        )
        form_edicao.request = type("obj", (object,), {"user": self.gestor})()

        self.assertTrue(form_edicao.is_valid())
