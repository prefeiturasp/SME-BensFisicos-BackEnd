from dados_comuns.tests.auth_test_utils import auth_kwargs
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
    MENSAGEM_SEM_PONTO_CENTRAL,
    MovimentacaoBemPatrimonialForm,
)
from bem_patrimonial.constants import APROVADO
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
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
            **auth_kwargs("test123"),
            is_staff=True,
            unidade_orcamentaria=self.ua1.unidade_orcamentaria,
        )
        self.gestor.groups.add(self.grupo_gestor)

        self.operador_ua1 = Usuario.objects.create_user(
            username="operador_ua1",
            email="operador_ua1@test.com",
            **auth_kwargs("test123"),
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
        self.assertIn("get_unidade_orcamentaria_destino", readonly_edicao)
        self.assertIn("unidade_administrativa_origem", readonly_edicao)
        self.assertIn("unidade_administrativa_destino", readonly_edicao)

        readonly_criacao = self.admin.get_readonly_fields(request, obj=None)
        self.assertEqual(len(readonly_criacao), 0)

    def test_form_de_edicao_instancia_sem_keyerror_com_campos_readonly(self):
        request = self.factory.get(
            "/admin/bem_patrimonial/movimentacaobempatrimonial/1/change/"
        )
        request.user = self.gestor

        form_class = self.admin.get_form(request, obj=self.movimentacao)
        form = form_class(instance=self.movimentacao)

        self.assertIn("unidade_orcamentaria_destino", form.fields)
        self.assertTrue(form.fields["unidade_orcamentaria_destino"].disabled)
        self.assertNotIn("unidade_administrativa_origem", form.fields)
        self.assertNotIn("unidade_administrativa_destino", form.fields)

    def test_campo_uo_destino_exibido_entre_origem_e_destino(self):
        request = self.factory.get("/admin/bem_patrimonial/movimentacaobempatrimonial/add/")
        request.user = self.gestor

        fields = self.admin.get_fields(request)

        self.assertEqual(fields[0], "unidade_administrativa_origem")
        self.assertEqual(fields[1], "unidade_orcamentaria_destino")
        self.assertEqual(fields[2], "unidade_administrativa_destino")

    def test_validacao_uas_so_acontece_na_criacao(self):
        form_criacao = MovimentacaoBemPatrimonialForm(
            data={
                "unidade_administrativa_origem": self.ua1.pk,
                "unidade_administrativa_destino": self.ua1.pk,  # Mesma UA - inválido
                "observacao": "Teste",
            },
            request=type("obj", (object,), {"user": self.gestor})(),
        )

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
            request=type("obj", (object,), {"user": self.gestor})(),
        )

        self.assertTrue(form_edicao.is_valid())

    def test_uo_destino_padrao_e_uo_do_usuario(self):
        form = MovimentacaoBemPatrimonialForm(request=type("obj", (object,), {"user": self.gestor})())

        self.assertEqual(
            form.fields["unidade_orcamentaria_destino"].initial,
            self.gestor.unidade_orcamentaria_id,
        )

    def test_uo_externa_preenche_ua_001_automaticamente(self):
        outra_uo = criar_uo(
            codigo="01.16.11",
            nome="UO Destino Externa",
            sigla="UO3",
        )
        criar_ua(
            uo=outra_uo,
            codigo="01.16.11.001",
            nome="Ponto Central",
            sigla="PC",
        )

        form = MovimentacaoBemPatrimonialForm(
            data={
                "unidade_administrativa_origem": self.ua1.pk,
                "unidade_orcamentaria_destino": outra_uo.pk,
                "observacao": "Teste UO externa",
            },
            request=type("obj", (object,), {"user": self.gestor})(),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["unidade_administrativa_destino"].codigo,
            "01.16.11.001",
        )
        self.assertEqual(
            form.cleaned_data["unidade_administrativa_destino"].unidade_orcamentaria,
            outra_uo,
        )

    def test_uo_externa_sem_ponto_central_exibe_erro_amigavel(self):
        uo_sem_ponto = criar_uo(
            codigo="01.16.12",
            nome="UO Sem Central",
            sigla="UO4",
        )
        criar_ua(
            uo=uo_sem_ponto,
            codigo="01.16.12.010",
            nome="UA Secundária",
            sigla="SEC",
        )

        form = MovimentacaoBemPatrimonialForm(
            data={
                "unidade_administrativa_origem": self.ua1.pk,
                "unidade_orcamentaria_destino": uo_sem_ponto.pk,
                "observacao": "Teste UO sem central",
            },
            request=type("obj", (object,), {"user": self.gestor})(),
        )

        self.assertFalse(form.is_valid())
        self.assertIn(MENSAGEM_SEM_PONTO_CENTRAL, str(form.errors))
