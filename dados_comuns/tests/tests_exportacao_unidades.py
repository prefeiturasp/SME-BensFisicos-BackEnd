from dados_comuns.tests.auth_test_utils import auth_kwargs
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.admin import UnidadeAdministrativaAdmin
from dados_comuns.formats import UnidadeAdministrativaPDFFormat
from dados_comuns.resources import UnidadeAdministrativaResource
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class ExportacaoUnidadeAdministrativaTestCase(TestCase):

    def setUp(self):
        uo = criar_uo(codigo="100", nome="UO 100")
        criar_ua(
            uo=uo,
            codigo="01.01.01.0001",
            sigla="SME",
            nome="Secretaria Municipal de Educação",
            status=UnidadeAdministrativa.ATIVA,
        )
        criar_ua(
            uo=uo,
            codigo="01.01.02.0002",
            sigla="PMSP/SME/SME-GAB/MEMORIAL",
            nome="COORDENADORIA DOS CENTROS EDUCACIONAIS UNIFICADOS",
            status=UnidadeAdministrativa.INATIVA,
        )

        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)

        self.gestor_com_rf = Usuario.objects.create_user(
            username="gestor_rf",
            email="gestor.rf@test.com",
            **auth_kwargs("test123"),
            nome="José da Silva",
            rf="123456",
            is_staff=True,
        )
        self.gestor_com_rf.groups.add(grupo_gestor)

        self.gestor_sem_rf = Usuario.objects.create_user(
            username="gestor_sem_rf",
            email="gestor.sem.rf@test.com",
            **auth_kwargs("test123"),
            nome="Maria Santos",
            rf=None,
            is_staff=True,
        )
        self.gestor_sem_rf.groups.add(grupo_gestor)

        grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
        self.operador = Usuario.objects.create_user(
            username="operador",
            email="operador@test.com",
            **auth_kwargs("test123"),
            nome="Operador Teste",
            rf="654321",
            is_staff=True,
        )
        self.operador.groups.add(grupo_operador)

        self.site = AdminSite()
        self.admin = UnidadeAdministrativaAdmin(UnidadeAdministrativa, self.site)
        self.factory = RequestFactory()

    def _gerar_pdf(self, usuario, queryset=None):
        if queryset is None:
            queryset = UnidadeAdministrativa.objects.all()

        request = self.factory.get("/admin/dados_comuns/unidadeadministrativa/")
        request.user = usuario

        pdf_format = UnidadeAdministrativaPDFFormat()
        pdf_format._export_request = request
        pdf_format._export_queryset = queryset

        return pdf_format.export_data(None)

    def test_pdf_gerado_com_estrutura_valida(self):
        pdf_bytes = self._gerar_pdf(self.gestor_com_rf)

        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"%%EOF", pdf_bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertIn(b"/Author (gestor_rf)", pdf_bytes)

    def test_pdf_gerado_sem_rf_cadastrado(self):
        pdf_bytes = self._gerar_pdf(self.gestor_sem_rf)

        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"%%EOF", pdf_bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertIn(b"/Author (gestor_sem_rf)", pdf_bytes)

    def test_exportacao_excel_com_status_legivel(self):
        resource = UnidadeAdministrativaResource()
        dataset = resource.export(UnidadeAdministrativa.objects.all())

        self.assertEqual(len(dataset), 2)
        status_values = [row[3] for row in dataset]
        self.assertIn("Ativa", status_values)
        self.assertIn("Inativa", status_values)

    def test_formatos_exportacao_disponiveis(self):
        formats = self.admin.get_export_formats()
        format_titles = [f().get_title() for f in formats]

        self.assertIn("csv", format_titles)
        self.assertIn("xlsx", format_titles)
        self.assertIn("pdf", format_titles)

    def test_importacao_desabilitada(self):
        request = self.factory.get("/admin/dados_comuns/unidadeadministrativa/")
        request.user = self.gestor_com_rf

        self.assertFalse(self.admin.has_import_permission(request))

    def test_campos_exportados_ordem_correta(self):
        resource = UnidadeAdministrativaResource()
        expected_order = ("codigo", "sigla", "nome", "status_display")

        self.assertEqual(resource.Meta.export_order, expected_order)

    def test_pdf_paginacao_multiplas_paginas(self):
        uo = criar_uo(codigo="99.99.00", nome="UO 99.99.00.0000")
        for i in range(50):
            criar_ua(
                codigo=f"99.99.{i:02d}.{i:04d}",
                sigla=f"UA-{i:03d}",
                nome=f"Unidade Administrativa de Teste {i}",
                status=UnidadeAdministrativa.ATIVA,
                uo=uo,
            )

        pdf_bytes = self._gerar_pdf(self.gestor_com_rf)

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"%%EOF", pdf_bytes)

        page_count = pdf_bytes.count(b"/Page")
        self.assertGreater(page_count, 1)

    def test_operador_nao_pode_exportar(self):
        request = self.factory.get("/admin/dados_comuns/unidadeadministrativa/")
        request.user = self.operador

        self.assertFalse(self.admin.has_export_permission(request))

    def test_gestor_pode_exportar(self):
        request = self.factory.get("/admin/dados_comuns/unidadeadministrativa/")
        request.user = self.gestor_com_rf

        self.assertTrue(self.admin.has_export_permission(request))

    def test_quantidade_registros_exportados(self):
        resource = UnidadeAdministrativaResource()
        queryset = UnidadeAdministrativa.objects.all()
        dataset = resource.export(queryset)

        total_esperado = queryset.count()
        linhas_dados = [row for row in dataset if row != dataset.headers]

        self.assertEqual(len(linhas_dados), total_esperado)
