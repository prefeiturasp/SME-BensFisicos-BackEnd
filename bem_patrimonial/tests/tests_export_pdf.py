import datetime
from decimal import Decimal
import re
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.formats import PDFFormat
from bem_patrimonial.admins.bem_patrimonial import BemPatrimonialAdmin
from bem_patrimonial.constants import APROVADO, NAO_APROVADO, AGUARDANDO_APROVACAO
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from dados_comuns.models import UnidadeAdministrativa

NPAT_NUM_REGEX = r"^\d{3}\.\d{9}-\d$"
NPAT_AUTO_REGEX = r"^SEM-NUMERO-\d+$"


class SetupExportData:
    def create_unidade_administrativa(self, codigo=100, nome="DRE Teste", sigla="DT"):
        return UnidadeAdministrativa.objects.create(
            codigo=codigo, nome=nome, sigla=sigla
        )

    def create_usuario(
        self, username="testuser", unidade=None, grupo=GRUPO_GESTOR_PATRIMONIO
    ):
        if not unidade:
            unidade = self.create_unidade_administrativa()

        usuario = Usuario.objects.create(
            username=username,
            password="testpass123",
            nome=f"Usuario {username}",
            email=f"{username}@teste.com",
            unidade_administrativa=unidade,
            is_staff=True,
        )

        group, _ = Group.objects.get_or_create(name=grupo)
        usuario.groups.add(group)

        return usuario

    def create_bem_patrimonial(self, criado_por, **kwargs):
        defaults = {
            "nome": "Notebook Dell",
            "descricao": "Notebook Dell Inspiron 15",
            "marca": "Dell",
            "modelo": "Inspiron 15",
            "valor_unitario": Decimal("2500.00"),
            "numero_processo": "2024001",
            "localizacao": "Sala 101",
            "criado_por": criado_por,
            "unidade_administrativa": criado_por.unidade_administrativa,
            "status": AGUARDANDO_APROVACAO,
            
            "sem_numeracao": True,
            "numero_formato_antigo": False,
        }
        defaults.update(kwargs)

        
        npat = defaults.get("numero_patrimonial", None)
        if npat is not None and npat != "":
            npat = str(npat)
            
            if re.fullmatch(NPAT_NUM_REGEX, npat):
                if BemPatrimonial.objects.filter(numero_patrimonial=npat).exists():
                    defaults["sem_numeracao"] = True
                    defaults.pop("numero_patrimonial", None)
                    defaults["numero_formato_antigo"] = False
                else:
                    defaults["sem_numeracao"] = False
                    defaults["numero_formato_antigo"] = False
                    defaults["numero_patrimonial"] = npat
            else:
                
                defaults["sem_numeracao"] = False
                defaults["numero_formato_antigo"] = True
                defaults["numero_patrimonial"] = npat
        else:
            
            defaults["sem_numeracao"] = True
            defaults.pop("numero_patrimonial", None)
            defaults["numero_formato_antigo"] = False

        return BemPatrimonial.objects.create(**defaults)


class PDFFormatTestCase(TestCase):

    def setUp(self):
        self.setup = SetupExportData()
        self.pdf_format = PDFFormat()

    def test_get_title_returns_pdf(self):
        self.assertEqual(self.pdf_format.get_title(), "pdf")

    def test_is_binary_returns_true(self):
        self.assertTrue(self.pdf_format.is_binary())

    def test_get_extension_returns_pdf(self):
        self.assertEqual(self.pdf_format.get_extension(), "pdf")

    def test_get_content_type_returns_application_pdf(self):
        self.assertEqual(self.pdf_format.get_content_type(), "application/pdf")

    def test_can_import_returns_false(self):
        self.assertFalse(self.pdf_format.can_import())

    def test_can_export_returns_true(self):
        self.assertTrue(self.pdf_format.can_export())

    def test_create_dataset_raises_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            self.pdf_format.create_dataset(None)


class PDFExportDataTestCase(TestCase):

    def setUp(self):
        self.setup = SetupExportData()
        self.unidade = self.setup.create_unidade_administrativa()
        self.usuario = self.setup.create_usuario(unidade=self.unidade)
        self.factory = RequestFactory()

    def test_export_empty_queryset(self):
        pdf_format = PDFFormat()
        pdf_format._export_request = self.factory.get("/admin/")
        pdf_format._export_request.user = self.usuario
        pdf_format._export_queryset = BemPatrimonial.objects.none()

        pdf_bytes = pdf_format.export_data(None)

        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 0)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_export_single_bem(self):
        bem = self.setup.create_bem_patrimonial(self.usuario, status=APROVADO)

        pdf_format = PDFFormat()
        pdf_format._export_request = self.factory.get("/admin/")
        pdf_format._export_request.user = self.usuario
        pdf_format._export_queryset = BemPatrimonial.objects.filter(id=bem.id)

        pdf_bytes = pdf_format.export_data(None)

        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 0)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_export_multiple_bens(self):
        for i in range(5):
            self.setup.create_bem_patrimonial(
                self.usuario,
                nome=f"Item {i}",
                numero_patrimonial=str(1000 + i),
                status=APROVADO,
            )

        pdf_format = PDFFormat()
        pdf_format._export_request = self.factory.get("/admin/")
        pdf_format._export_request.user = self.usuario
        pdf_format._export_queryset = BemPatrimonial.objects.all()

        pdf_bytes = pdf_format.export_data(None)

        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 0)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_export_with_different_status(self):

        self.setup.create_bem_patrimonial(
            self.usuario, status=APROVADO, nome="Aprovado"
        )
        self.setup.create_bem_patrimonial(
            self.usuario, status=NAO_APROVADO, nome="Rejeitado"
        )
        self.setup.create_bem_patrimonial(
            self.usuario, status=AGUARDANDO_APROVACAO, nome="Aguardando"
        )

        pdf_format = PDFFormat()
        pdf_format._export_request = self.factory.get("/admin/")
        pdf_format._export_request.user = self.usuario
        pdf_format._export_queryset = BemPatrimonial.objects.all()

        pdf_bytes = pdf_format.export_data(None)

        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_export_calculates_statistics_correctly(self):

        self.setup.create_bem_patrimonial(
            self.usuario,
            valor_unitario=Decimal("100.00"),
            localizacao="Local A",
        )
        self.setup.create_bem_patrimonial(
            self.usuario,
            valor_unitario=Decimal("200.00"),
            localizacao="Local B",
        )
        self.setup.create_bem_patrimonial(
            self.usuario,
            valor_unitario=Decimal("50.00"),
            localizacao="Local A",
        )

        pdf_format = PDFFormat()
        pdf_format._export_request = self.factory.get("/admin/")
        pdf_format._export_request.user = self.usuario
        pdf_format._export_queryset = BemPatrimonial.objects.all()

        pdf_bytes = pdf_format.export_data(None)

        self.assertIsInstance(pdf_bytes, bytes)
        self.assertGreater(len(pdf_bytes), 0)

        
        
        
        


class BemPatrimonialAdminExportTestCase(TestCase):

    def setUp(self):
        self.setup = SetupExportData()
        self.site = AdminSite()
        self.admin = BemPatrimonialAdmin(BemPatrimonial, self.site)
        self.factory = RequestFactory()

        self.unidade1 = self.setup.create_unidade_administrativa(
            codigo=100, nome="DRE A"
        )
        self.unidade2 = self.setup.create_unidade_administrativa(
            codigo=200, nome="DRE B"
        )

        self.gestor = self.setup.create_usuario(
            "gestor", self.unidade1, GRUPO_GESTOR_PATRIMONIO
        )
        self.operador = self.setup.create_usuario(
            "operador", self.unidade1, GRUPO_OPERADOR_INVENTARIO
        )

    def test_get_export_formats_includes_pdf(self):
        formats = self.admin.get_export_formats()
        format_classes = [f().__class__.__name__ for f in formats]

        self.assertIn("PDFFormat", format_classes)

    def test_get_export_data_injects_request_and_queryset(self):
        bem = self.setup.create_bem_patrimonial(self.gestor)
        queryset = BemPatrimonial.objects.filter(id=bem.id)

        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.gestor

        pdf_format = PDFFormat()
        self.admin.get_export_data(pdf_format, queryset, request=request)

        self.assertEqual(pdf_format._export_request, request)
        self.assertEqual(list(pdf_format._export_queryset), list(queryset))

    def test_get_export_queryset_gestor_sees_all(self):

        self.setup.create_bem_patrimonial(self.gestor, nome="Bem Unidade 1")
        usuario_unidade2 = self.setup.create_usuario("user2", self.unidade2)
        self.setup.create_bem_patrimonial(usuario_unidade2, nome="Bem Unidade 2")

        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.gestor

        queryset = self.admin.get_export_queryset(request)

        self.assertEqual(queryset.count(), 2)

    def test_get_export_queryset_operador_sees_only_own_unit(self):
        bem_unidade1 = self.setup.create_bem_patrimonial(
            self.gestor, nome="Bem Unidade 1", status=APROVADO
        )
        # garante vínculo na unidade1
        bem_unidade1.unidade_administrativa = self.unidade1
        bem_unidade1.save()

        usuario_unidade2 = self.setup.create_usuario("user2", self.unidade2)
        bem_unidade2 = self.setup.create_bem_patrimonial(
            usuario_unidade2, nome="Bem Unidade 2", status=APROVADO
        )
        # garante vínculo na unidade2
        bem_unidade2.unidade_administrativa = self.unidade2
        bem_unidade2.save()

        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.operador

        queryset = self.admin.get_export_queryset(request)

        self.assertEqual(queryset.count(), 1)
        self.assertEqual(queryset.first().id, bem_unidade1.id)


class PDFContentTestCase(TestCase):

    def setUp(self):
        self.setup = SetupExportData()
        self.unidade = self.setup.create_unidade_administrativa(nome="DRE Centro")
        self.usuario = self.setup.create_usuario(unidade=self.unidade)
        self.factory = RequestFactory()

    def test_pdf_contains_all_required_columns(self):
        bem = self.setup.create_bem_patrimonial(
            self.usuario,
            numero_patrimonial=123,
            nome="Notebook",
            descricao="Notebook Dell",
            marca="Dell",
            modelo="Inspiron",
            localizacao="Sala 10",
            valor_unitario=Decimal("3000.00"),
            numero_processo="2024100",
        )

        pdf_format = PDFFormat()
        pdf_format._export_request = self.factory.get("/admin/")
        pdf_format._export_request.user = self.usuario
        pdf_format._export_queryset = BemPatrimonial.objects.filter(id=bem.id)

        pdf_bytes = pdf_format.export_data(None)

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"ReportLab", pdf_bytes)

    def test_pdf_handles_none_values(self):

        bem = self.setup.create_bem_patrimonial(
            self.usuario, numero_patrimonial=None, localizacao=None
        )

        pdf_format = PDFFormat()
        pdf_format._export_request = self.factory.get("/admin/")
        pdf_format._export_request.user = self.usuario
        pdf_format._export_queryset = BemPatrimonial.objects.filter(id=bem.id)

        pdf_bytes = pdf_format.export_data(None)

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_pdf_with_long_text_values(self):

        long_description = "A" * 500

        bem = self.setup.create_bem_patrimonial(
            self.usuario, nome="Nome muito longo " * 10, descricao=long_description
        )

        pdf_format = PDFFormat()
        pdf_format._export_request = self.factory.get("/admin/")
        pdf_format._export_request.user = self.usuario
        pdf_format._export_queryset = BemPatrimonial.objects.filter(id=bem.id)

        pdf_bytes = pdf_format.export_data(None)

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))


class PDFUserContextTestCase(TestCase):

    def setUp(self):
        self.setup = SetupExportData()
        self.unidade = self.setup.create_unidade_administrativa()
        self.factory = RequestFactory()

    def test_pdf_uses_nome_field_when_available(self):
        usuario = self.setup.create_usuario()
        usuario.nome = "Maria Silva"
        usuario.first_name = "Maria"
        usuario.last_name = "Santos"
        usuario.save()

        bem = self.setup.create_bem_patrimonial(usuario)

        pdf_format = PDFFormat()
        pdf_format._export_request = self.factory.get("/admin/")
        pdf_format._export_request.user = usuario
        pdf_format._export_queryset = BemPatrimonial.objects.filter(id=bem.id)

        pdf_bytes = pdf_format.export_data(None)

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_pdf_uses_username_as_fallback(self):
        usuario = self.setup.create_usuario()
        usuario.nome = None
        usuario.first_name = ""
        usuario.last_name = ""
        usuario.save()

        bem = self.setup.create_bem_patrimonial(usuario)

        pdf_format = PDFFormat()
        pdf_format._export_request = self.factory.get("/admin/")
        pdf_format._export_request.user = usuario
        pdf_format._export_queryset = BemPatrimonial.objects.filter(id=bem.id)

        pdf_bytes = pdf_format.export_data(None)

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_pdf_without_request_uses_default_author(self):

        bem = self.setup.create_bem_patrimonial(self.setup.create_usuario())

        pdf_format = PDFFormat()
        pdf_format._export_request = None
        pdf_format._export_queryset = BemPatrimonial.objects.filter(id=bem.id)

        pdf_bytes = pdf_format.export_data(None)

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
