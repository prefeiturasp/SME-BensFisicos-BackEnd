from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.admins.bem_patrimonial import BemPatrimonialAdmin
from bem_patrimonial.constants import APROVADO
from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class EdicaoRestritaOperadorTestCase(TestCase):

    def setUp(self):
        self.grupo_gestor = Group.objects.create(name=GRUPO_GESTOR_PATRIMONIO)
        self.grupo_operador = Group.objects.create(name=GRUPO_OPERADOR_INVENTARIO)

        self.ua1 = UnidadeAdministrativa.objects.create(
            codigo="UA001",
            nome="Unidade 1",
            sigla="U1",
            status=UnidadeAdministrativa.ATIVA,
        )
        self.ua2 = UnidadeAdministrativa.objects.create(
            codigo="UA002",
            nome="Unidade 2",
            sigla="U2",
            status=UnidadeAdministrativa.ATIVA,
        )

        self.gestor = Usuario.objects.create_user(
            username="gestor",
            email="gestor@test.com",
            password="test123",
            is_staff=True,
        )
        self.gestor.groups.add(self.grupo_gestor)

        self.operador_ua1 = Usuario.objects.create_user(
            username="operador_ua1",
            email="operador_ua1@test.com",
            password="test123",
            is_staff=True,
            unidade_administrativa=self.ua1,
        )
        self.operador_ua1.groups.add(self.grupo_operador)

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

        FormClass = self.admin.get_form(request, obj=self.bem_ua1)

        form_data = {
            "localizacao": "Sala 202 - ALTERADA",
        }

        form = FormClass(data=form_data, instance=self.bem_ua1)

        is_valid = form.is_valid()
        if not is_valid:
            print(f"Erros do form: {form.errors}")

        self.assertTrue(is_valid, f"Form deveria ser válido. Erros: {form.errors}")

        bem_editado = form.save()
        self.assertEqual(bem_editado.localizacao, "Sala 202 - ALTERADA")

    def test_form_nao_tem_campos_readonly_no_init(self):
        request = self.factory.post("/admin/")
        request.user = self.operador_ua1

        FormClass = self.admin.get_form(request, obj=self.bem_ua1)

        form_data = {
            "localizacao": "Sala 999",
        }

        form = FormClass(data=form_data, instance=self.bem_ua1)

        self.assertNotIn("nome", form.fields)
        self.assertNotIn("valor_unitario", form.fields)
        self.assertNotIn("marca", form.fields)
        self.assertNotIn("numero_patrimonial", form.fields)
        self.assertNotIn("unidade_administrativa", form.fields)

        self.assertIn("localizacao", form.fields)

    def test_gestor_consegue_editar_multiplos_campos(self):
        request = self.factory.post("/admin/")
        request.user = self.gestor

        FormClass = self.admin.get_form(request, obj=self.bem_ua1)

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
        }

        form = FormClass(data=form_data, instance=self.bem_ua1)

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
            password="test123",
            is_staff=True,
            unidade_administrativa=self.ua2,
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
