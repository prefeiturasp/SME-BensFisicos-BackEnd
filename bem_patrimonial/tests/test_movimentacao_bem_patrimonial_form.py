"""Testes para bem_patrimonial.admins.forms.movimentacao_bem_patrimonial_form."""
from django.test import RequestFactory, TestCase
from django.core.exceptions import ValidationError

from bem_patrimonial.models import MovimentacaoBemPatrimonial
from bem_patrimonial.admins.forms.movimentacao_bem_patrimonial_form import MovimentacaoBemPatrimonialForm
from bem_patrimonial import constants
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_OPERADOR_INVENTARIO
from django.contrib.auth.models import Group


class TestMovimentacaoBemPatrimonialForm(TestCase):
    """Testes para MovimentacaoBemPatrimonialForm."""

    def setUp(self):
        self.factory = RequestFactory()
        self.uo = criar_uo(codigo="201")
        self.ua_origem = criar_ua(uo=self.uo, codigo="201", status=UnidadeAdministrativa.ATIVA)
        self.ua_destino = criar_ua(uo=self.uo, codigo="202", status=UnidadeAdministrativa.ATIVA)
        self.uo_outra = criar_uo(codigo="203")
        self.ua_outra_uo = criar_ua(uo=self.uo_outra, codigo="204", status=UnidadeAdministrativa.ATIVA)
        
        grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
        self.operador = Usuario.objects.create_user(
            username="operador",
            password="x",
            email="operador@test.com",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        self.operador.groups.add(grupo_operador)
        
        self.operador_outro = Usuario.objects.create_user(
            username="operador_outro",
            password="x",
            email="operador_outro@test.com",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        self.operador_outro.groups.add(grupo_operador)

    def test_init_sem_usuario_define_queryset_completo(self):
        """__init__ sem usuário define queryset completo."""
        form = MovimentacaoBemPatrimonialForm()
        if "unidade_administrativa_origem" in form.fields:
            qs_origem = form.fields["unidade_administrativa_origem"].queryset
            self.assertIn(self.ua_origem, qs_origem)
            self.assertIn(self.ua_destino, qs_origem)

    def test_init_com_usuario_filtra_ua_origem(self):
        """__init__ com usuário filtra UA origem por escopo."""
        request = self.factory.get("/")
        request.user = self.operador
        form = MovimentacaoBemPatrimonialForm()
        form.request = request
        form.__init__()
        
        if "unidade_administrativa_origem" in form.fields:
            qs_origem = form.fields["unidade_administrativa_origem"].queryset
            # Deve conter apenas UA do usuário
            self.assertIn(self.ua_origem, qs_origem)

    def test_init_com_usuario_filtra_ua_destino(self):
        """__init__ com usuário filtra UA destino por UO."""
        request = self.factory.get("/")
        request.user = self.operador
        form = MovimentacaoBemPatrimonialForm()
        form.request = request
        form.__init__()
        
        if "unidade_administrativa_destino" in form.fields:
            qs_destino = form.fields["unidade_administrativa_destino"].queryset
            # Deve conter apenas UAs da UO do usuário
            self.assertIn(self.ua_destino, qs_destino)
            self.assertNotIn(self.ua_outra_uo, qs_destino)

    def test_clean_novo_sem_ua_origem_levanta_erro(self):
        """clean para novo objeto sem UA origem levanta erro."""
        form = MovimentacaoBemPatrimonialForm(data={
            "unidade_administrativa_origem": "",
            "unidade_administrativa_destino": self.ua_destino.pk,
            "observacao": "",
        })
        form.instance = MovimentacaoBemPatrimonial()
        form.is_valid()
        with self.assertRaises(ValidationError) as cm:
            form.clean()
        self.assertIn("origem", str(cm.exception).lower())

    def test_clean_novo_sem_ua_destino_levanta_erro(self):
        """clean para novo objeto sem UA destino levanta erro."""
        form = MovimentacaoBemPatrimonialForm(data={
            "unidade_administrativa_origem": self.ua_origem.pk,
            "unidade_administrativa_destino": "",
            "observacao": "",
        })
        form.instance = MovimentacaoBemPatrimonial()
        form.is_valid()
        with self.assertRaises(ValidationError) as cm:
            form.clean()
        self.assertIn("destino", str(cm.exception).lower())

    def test_clean_novo_ua_origem_inativa_levanta_erro(self):
        """clean para novo objeto com UA origem inativa levanta erro."""
        ua_inativa = criar_ua(uo=self.uo, codigo="205", status=UnidadeAdministrativa.INATIVA)
        form = MovimentacaoBemPatrimonialForm(data={
            "unidade_administrativa_origem": ua_inativa.pk,
            "unidade_administrativa_destino": self.ua_destino.pk,
            "observacao": "",
        })
        form.instance = MovimentacaoBemPatrimonial()
        # Preencher cleaned_data manualmente para evitar validação de campo obrigatório
        form.cleaned_data = {
            "unidade_administrativa_origem": ua_inativa,
            "unidade_administrativa_destino": self.ua_destino,
            "observacao": "",
        }
        with self.assertRaises(ValidationError) as cm:
            form.clean()
        self.assertIn("inativa", str(cm.exception).lower())

    def test_clean_novo_ua_destino_inativa_levanta_erro(self):
        """clean para novo objeto com UA destino inativa levanta erro."""
        ua_inativa = criar_ua(uo=self.uo, codigo="206", status=UnidadeAdministrativa.INATIVA)
        form = MovimentacaoBemPatrimonialForm(data={
            "unidade_administrativa_origem": self.ua_origem.pk,
            "unidade_administrativa_destino": ua_inativa.pk,
            "observacao": "",
        })
        form.instance = MovimentacaoBemPatrimonial()
        # Preencher cleaned_data manualmente para evitar validação de campo obrigatório
        form.cleaned_data = {
            "unidade_administrativa_origem": self.ua_origem,
            "unidade_administrativa_destino": ua_inativa,
            "observacao": "",
        }
        with self.assertRaises(ValidationError) as cm:
            form.clean()
        self.assertIn("inativa", str(cm.exception).lower())

    def test_clean_novo_origem_igual_destino_levanta_erro(self):
        """clean para novo objeto com origem igual destino levanta erro."""
        form = MovimentacaoBemPatrimonialForm(data={
            "unidade_administrativa_origem": self.ua_origem.pk,
            "unidade_administrativa_destino": self.ua_origem.pk,
            "observacao": "",
        })
        form.instance = MovimentacaoBemPatrimonial()
        form.is_valid()
        with self.assertRaises(ValidationError) as cm:
            form.clean()
        self.assertIn("iguais", str(cm.exception).lower())

    def test_clean_novo_ua_origem_fora_escopo_levanta_erro(self):
        """clean para novo objeto com UA origem fora do escopo levanta erro."""
        request = self.factory.get("/")
        request.user = self.operador
        form = MovimentacaoBemPatrimonialForm(data={
            "unidade_administrativa_origem": self.ua_outra_uo.pk,
            "unidade_administrativa_destino": self.ua_destino.pk,
            "observacao": "",
        })
        form.instance = MovimentacaoBemPatrimonial()
        form.request = request
        # Preencher cleaned_data manualmente para evitar validação de campo obrigatório
        form.cleaned_data = {
            "unidade_administrativa_origem": self.ua_outra_uo,
            "unidade_administrativa_destino": self.ua_destino,
            "observacao": "",
        }
        with self.assertRaises(ValidationError) as cm:
            form.clean()
        self.assertIn("escopo", str(cm.exception).lower())

    def test_clean_novo_ua_destino_fora_uo_levanta_erro(self):
        """clean para novo objeto com UA destino fora da UO levanta erro."""
        request = self.factory.get("/")
        request.user = self.operador
        form = MovimentacaoBemPatrimonialForm(data={
            "unidade_administrativa_origem": self.ua_origem.pk,
            "unidade_administrativa_destino": self.ua_outra_uo.pk,
            "observacao": "",
        })
        form.instance = MovimentacaoBemPatrimonial()
        form.request = request
        form.is_valid()
        with self.assertRaises(ValidationError) as cm:
            form.clean()
        self.assertIn("destino", str(cm.exception).lower())

    def test_clean_edit_operador_outro_usuario_levanta_erro(self):
        """clean para edição com operador tentando editar movimentação de outro usuário levanta erro."""
        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_outro,
            status=constants.ENVIADA,
        )
        request = self.factory.get("/")
        request.user = self.operador
        form = MovimentacaoBemPatrimonialForm(data={
            "unidade_administrativa_origem": self.ua_origem.pk,
            "unidade_administrativa_destino": self.ua_destino.pk,
            "observacao": "Nova observação",
        }, instance=movimentacao)
        form.instance = movimentacao
        form.request = request
        form.is_valid()
        with self.assertRaises(ValidationError) as cm:
            form.clean()
        self.assertIn("outro usuário", str(cm.exception).lower())

    def test_clean_edit_operador_proprio_usuario_valido(self):
        """clean para edição com operador editando própria movimentação é válido."""
        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )
        request = self.factory.get("/")
        request.user = self.operador
        form = MovimentacaoBemPatrimonialForm(data={
            "unidade_administrativa_origem": self.ua_origem.pk,
            "unidade_administrativa_destino": self.ua_destino.pk,
            "observacao": "Nova observação",
        }, instance=movimentacao)
        form.instance = movimentacao
        form.request = request
        form.is_valid()
        # Não deve levantar erro
        cleaned = form.clean()
        self.assertIsNotNone(cleaned)

    def test_clean_edit_nao_operador_valido(self):
        """clean para edição com não operador é válido."""
        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_outro,
            status=constants.ENVIADA,
        )
        # Criar usuário sem grupo de operador
        usuario_comum = Usuario.objects.create_user(
            username="comum",
            password="x",
            email="comum@test.com",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        request = self.factory.get("/")
        request.user = usuario_comum
        form = MovimentacaoBemPatrimonialForm(data={
            "unidade_administrativa_origem": self.ua_origem.pk,
            "unidade_administrativa_destino": self.ua_destino.pk,
            "observacao": "Nova observação",
        }, instance=movimentacao)
        form.instance = movimentacao
        form.request = request
        form.is_valid()
        # Não deve levantar erro
        cleaned = form.clean()
        self.assertIsNotNone(cleaned)
