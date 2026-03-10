from dados_comuns.tests.auth_test_utils import auth_kwargs
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.admins.bem_patrimonial import BemPatrimonialAdmin
from bem_patrimonial.constants import APROVADO
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class EdicaoRestritaOperadorTestCase(TestCase):

    def setUp(self):
        self.grupo_gestor = Group.objects.create(name=GRUPO_GESTOR_PATRIMONIO)
        self.grupo_operador = Group.objects.create(name=GRUPO_OPERADOR_INVENTARIO)
        self.uo = criar_uo(codigo="100", nome="UO 100")

        self.ua1 = criar_ua(
            codigo="UA001",
            nome="Unidade 1",
            sigla="U1",
            status=UnidadeAdministrativa.ATIVA,
            uo=self.uo,
        )
        self.ua2 = criar_ua(
            codigo="UA002",
            nome="Unidade 2",
            sigla="U2",
            status=UnidadeAdministrativa.ATIVA,
            uo=self.uo,
        )

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

        self.bem_ua1 = BemPatrimonial.objects.create(
            nome="Computador",
            descricao="Desktop Dell",
            valor_unitario=2000.00,
            marca="Dell",
            modelo="OptiPlex",
            numero_processo="PROC-001",
            numero_patrimonial="000.000000001-0",
            localizacao="Sala 101",
            status=APROVADO,
            unidade_administrativa=self.ua1,
            criado_por=self.operador_ua1,
        )

        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = BemPatrimonialAdmin(BemPatrimonial, self.site)

    def test_gestor_tem_todos_campos_editaveis(self):
        request = self.factory.get("/admin/")
        request.user = self.gestor

        readonly = self.admin.get_readonly_fields(request, obj=self.bem_ua1)

        self.assertIn("status", readonly)
        self.assertIn("criado_por", readonly)
        self.assertIn("criado_em", readonly)

        self.assertNotIn("nome", readonly)
        self.assertNotIn("descricao", readonly)
        self.assertNotIn("valor_unitario", readonly)
        self.assertNotIn("marca", readonly)
        self.assertNotIn("modelo", readonly)
        self.assertNotIn("numero_patrimonial", readonly)
        self.assertNotIn("numero_processo", readonly)
        self.assertNotIn("foto", readonly)
        self.assertNotIn("localizacao", readonly)

    def test_operador_so_pode_editar_localizacao(self):
        request = self.factory.get("/admin/")
        request.user = self.operador_ua1

        readonly = self.admin.get_readonly_fields(request, obj=self.bem_ua1)

        self.assertIn("status", readonly)
        self.assertIn("criado_por", readonly)
        self.assertIn("criado_em", readonly)
        self.assertIn("nome", readonly)
        self.assertIn("descricao", readonly)
        self.assertIn("valor_unitario", readonly)
        self.assertIn("marca", readonly)
        self.assertIn("modelo", readonly)
        self.assertIn("numero_patrimonial", readonly)
        self.assertIn("numero_processo", readonly)
        self.assertIn("foto", readonly)

        self.assertNotIn("localizacao", readonly)

    def test_operador_consegue_editar_localizacao(self):
        request = self.factory.post("/admin/")
        request.user = self.operador_ua1

        form_class = self.admin.get_form(request, obj=self.bem_ua1)

        form_data = {
            "localizacao": "Sala 202 - ALTERADA",
        }

        form = form_class(data=form_data, instance=self.bem_ua1)

        is_valid = form.is_valid()
        if not is_valid:
            print(f"Erros do form: {form.errors}")

        self.assertTrue(is_valid, f"Form deveria ser válido. Erros: {form.errors}")

        bem_editado = form.save()
        self.assertEqual(bem_editado.localizacao, "Sala 202 - ALTERADA")

    def test_form_nao_tem_campos_readonly_no_init(self):
        request = self.factory.post("/admin/")
        request.user = self.operador_ua1

        form_class = self.admin.get_form(request, obj=self.bem_ua1)

        form_data = {
            "localizacao": "Sala 999",
        }

        form = form_class(data=form_data, instance=self.bem_ua1)

        self.assertNotIn("nome", form.fields)
        self.assertNotIn("valor_unitario", form.fields)
        self.assertNotIn("marca", form.fields)
        self.assertNotIn("numero_patrimonial", form.fields)
        self.assertNotIn("unidade_administrativa", form.fields)

        self.assertIn("localizacao", form.fields)

    def test_gestor_consegue_editar_multiplos_campos(self):
        request = self.factory.post("/admin/")
        request.user = self.gestor

        form_class = self.admin.get_form(request, obj=self.bem_ua1)

        form_data = {
            "nome": "Notebook HP",
            "descricao": "Notebook corporativo",
            "valor_unitario": "3500,00",
            "marca": "HP",
            "modelo": "EliteBook 840",
            "localizacao": "Sala 303",
            "numero_processo": "PROC-999",
            "numero_patrimonial": self.bem_ua1.numero_patrimonial,
            "unidade_administrativa": self.ua1.pk,
            "numero_formato_antigo": False,
            "sem_numeracao": False,
            "justificativa": "Teste"
        }

        form = form_class(data=form_data, instance=self.bem_ua1)

        is_valid = form.is_valid()
        if not is_valid:
            print(f"Erros do form: {form.errors}")

        self.assertTrue(is_valid, f"Form deveria ser válido. Erros: {form.errors}")

        bem_editado = form.save()
        self.assertEqual(bem_editado.nome, "Notebook HP")
        self.assertEqual(bem_editado.marca, "HP")
        self.assertEqual(bem_editado.localizacao, "Sala 303")

    def test_criacao_com_operador_permite_todos_campos(self):
        request = self.factory.get("/admin/")
        request.user = self.operador_ua1

        readonly = self.admin.get_readonly_fields(request, obj=None)

        self.assertIn("status", readonly)
        self.assertIn("criado_por", readonly)
        self.assertIn("criado_em", readonly)

        self.assertNotIn("nome", readonly)
        self.assertNotIn("descricao", readonly)
        self.assertNotIn("valor_unitario", readonly)
        self.assertNotIn("marca", readonly)
        self.assertNotIn("modelo", readonly)
        self.assertNotIn("numero_patrimonial", readonly)
        self.assertNotIn("numero_processo", readonly)
        self.assertNotIn("foto", readonly)
        self.assertNotIn("localizacao", readonly)

    def test_operador_diferente_ua_nao_ve_bem(self):
        operador_ua2 = Usuario.objects.create_user(
            username="operador_ua2",
            email="operador_ua2@test.com",
            **auth_kwargs("test123"),
            is_staff=True,
            unidade_administrativa=self.ua2,
            unidade_orcamentaria=self.ua2.unidade_orcamentaria,
        )
        operador_ua2.groups.add(self.grupo_operador)

        request = self.factory.get("/admin/")
        request.user = operador_ua2

        qs = self.admin.get_queryset(request)

        self.assertNotIn(self.bem_ua1, qs)

    def test_gestor_ve_todos_bens(self):
        request = self.factory.get("/admin/")
        request.user = self.gestor

        qs = self.admin.get_queryset(request)

        self.assertIn(self.bem_ua1, qs)

    def test_alterar_nome_sem_justificativa_deve_falhar(self):
        request = self.factory.post("/admin/")
        request.user = self.gestor

        form_class = self.admin.get_form(request, obj=self.bem_ua1)

        form_data = {
            "nome": "Nome Alterado",
            "descricao": self.bem_ua1.descricao,
            "valor_unitario": "2000,00",
            "marca": self.bem_ua1.marca,
            "modelo": self.bem_ua1.modelo,
            "localizacao": self.bem_ua1.localizacao,
            "numero_processo": self.bem_ua1.numero_processo,
            "numero_patrimonial": self.bem_ua1.numero_patrimonial,
            "unidade_administrativa": self.ua1.pk,
            "numero_formato_antigo": False,
            "sem_numeracao": False,
            # sem justificativa
        }

        form = form_class(data=form_data, instance=self.bem_ua1)

        self.assertFalse(form.is_valid())
        self.assertIn("justificativa", form.errors)

    def test_alterar_numero_patrimonial_sem_justificativa_deve_falhar(self):
        request = self.factory.post("/admin/")
        request.user = self.gestor

        form_class = self.admin.get_form(request, obj=self.bem_ua1)

        form_data = {
            "nome": self.bem_ua1.nome,
            "descricao": self.bem_ua1.descricao,
            "valor_unitario": "2000,00",
            "marca": self.bem_ua1.marca,
            "modelo": self.bem_ua1.modelo,
            "localizacao": self.bem_ua1.localizacao,
            "numero_processo": self.bem_ua1.numero_processo,
            "numero_patrimonial": "999.999999999-9",
            "unidade_administrativa": self.ua1.pk,
            "numero_formato_antigo": False,
            "sem_numeracao": False,
        }

        form = form_class(data=form_data, instance=self.bem_ua1)

        self.assertFalse(form.is_valid())
        self.assertIn("justificativa", form.errors)

    def test_alterar_apenas_localizacao_sem_justificativa_deve_passar(self):
        request = self.factory.post("/admin/")
        request.user = self.gestor

        form_class = self.admin.get_form(request, obj=self.bem_ua1)

        form_data = {
            "nome": self.bem_ua1.nome,
            "descricao": self.bem_ua1.descricao,
            "valor_unitario": "2000,00",
            "marca": self.bem_ua1.marca,
            "modelo": self.bem_ua1.modelo,
            "localizacao": "Nova sala 404",
            "numero_processo": self.bem_ua1.numero_processo,
            "numero_patrimonial": self.bem_ua1.numero_patrimonial,
            "unidade_administrativa": self.ua1.pk,
            "numero_formato_antigo": False,
            "sem_numeracao": False,
            # sem justificativa
        }

        form = form_class(data=form_data, instance=self.bem_ua1)

        self.assertTrue(form.is_valid(), form.errors)

    def test_observacao_nao_obrigatoria_na_criacao(self):
        request = self.factory.post("/admin/")
        request.user = self.operador_ua1

        form_class = self.admin.get_form(request, obj=None)

        form_data = {
            "nome": "Novo Bem",
            "descricao": "Descrição",
            "valor_unitario": "1500,00",
            "marca": "Lenovo",
            "modelo": "ThinkCentre",
            "localizacao": "Sala 505",
            "numero_processo": "PROC-NEW",
            "numero_patrimonial": "123.123123123-1",
            "unidade_administrativa": self.ua1.pk,
            "numero_formato_antigo": False,
            "sem_numeracao": False,
            # observacao ausente
        }

        form = form_class(data=form_data)

        self.assertTrue(form.is_valid(), form.errors)

    def test_save_model_recebe_justificativa(self):
        request = self.factory.post("/admin/", data={"justificativa": "Teste auditoria"})
        request.user = self.gestor

        form_class = self.admin.get_form(request, obj=self.bem_ua1)

        form_data = {
            "nome": self.bem_ua1.nome,
            "descricao": self.bem_ua1.descricao,
            "valor_unitario": "2000,00",
            "marca": self.bem_ua1.marca,
            "modelo": self.bem_ua1.modelo,
            "localizacao": "Sala alterada",
            "numero_processo": self.bem_ua1.numero_processo,
            "numero_patrimonial": self.bem_ua1.numero_patrimonial,
            "unidade_administrativa": self.ua1.pk,
            "numero_formato_antigo": False,
            "sem_numeracao": False,
            "justificativa": "Teste auditoria",
        }

        form = form_class(data=form_data, instance=self.bem_ua1)
        self.assertTrue(form.is_valid(), form.errors)

        obj = form.save(commit=False)
        self.admin.save_model(request, obj, form, change=True)

        self.assertEqual(getattr(obj, "_justificativa", None), "Teste auditoria")
