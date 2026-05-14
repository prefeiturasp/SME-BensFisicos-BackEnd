from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua, codigo_uo
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from unittest.mock import Mock
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria
from dados_comuns.admin import UnidadeAdministrativaAdmin
from dados_comuns.formats import UnidadeAdministrativaPDFFormat, UnidadeOrcamentariaPDFFormat
from dados_comuns.resources import UnidadeAdministrativaResource, UnidadeOrcamentariaResource
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class ExportacaoUnidadeAdministrativaTestCase(TestCase):

    def setUp(self):
        uo = criar_uo(codigo="100", nome="UO 100")
        criar_ua(
            uo=uo,
            codigo=codigo_ua(1, 1, 1, 1),
            sigla="SME",
            nome="Secretaria Municipal de Educação",
            status=UnidadeAdministrativa.ATIVA,
        )
        criar_ua(
            uo=uo,
            codigo=codigo_ua(1, 1, 2, 2),
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
        self.assertIn(b"/Author (123456)", pdf_bytes)

    def test_pdf_gerado_sem_rf_cadastrado(self):
        pdf_bytes = self._gerar_pdf(self.gestor_sem_rf)

        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"%%EOF", pdf_bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertIn(b"/Author (-)", pdf_bytes)

    def test_resolve_usuario_exportacao_retorna_apenas_rf(self):
        request = self.factory.get("/admin/dados_comuns/unidadeadministrativa/")
        request.user = self.gestor_com_rf

        pdf_format = UnidadeAdministrativaPDFFormat()

        self.assertEqual(pdf_format._resolver_usuario_exportacao(request), "123456")

    def test_rodape_pdf_exibe_apenas_rf(self):
        request = self.factory.get("/admin/dados_comuns/unidadeadministrativa/")
        request.user = self.gestor_com_rf

        pdf_format = UnidadeAdministrativaPDFFormat()
        pdf_format._export_request = request

        canvas = Mock()
        canvas.getPageNumber.return_value = 1
        doc = Mock()

        pdf_format._adicionar_numero_pagina(canvas, doc)

        footer_text = canvas.drawString.call_args.args[2]
        self.assertIn("Gerado por 123456 em ", footer_text)
        self.assertNotIn("José da Silva", footer_text)

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
        uo = criar_uo(codigo=codigo_uo(99, 99, 0), nome="UO 99")
        for i in range(50):
            criar_ua(
                codigo=codigo_ua(99, 99, i, i),
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


class ExportacaoUnidadeOrcamentariaTestCase(TestCase):

    def setUp(self):
        criar_uo(codigo=codigo_uo(10, 10, 10), nome="UO Ativa", sigla="ATV", ativa=True)
        criar_uo(codigo=codigo_uo(20, 20, 20), nome="UO Inativa", sigla="INA", ativa=False)

        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.superuser = Usuario.objects.create_user(
            username="super_export_uo",
            email="super.export.uo@test.com",
            **auth_kwargs("test123"),
            nome="Super Export UO",
            rf="777888",
            is_staff=True,
            is_superuser=True,
        )
        self.superuser.groups.add(grupo_gestor)

        self.factory = RequestFactory()

    def _gerar_pdf(self, usuario=None, queryset=None):
        if queryset is None:
            queryset = UnidadeOrcamentaria.objects.all()

        request = None
        if usuario is not None:
            request = self.factory.get("/api/unidades-orcamentarias/exportar/")
            request.user = usuario

        pdf_format = UnidadeOrcamentariaPDFFormat()
        pdf_format._export_request = request
        pdf_format._export_queryset = queryset
        return pdf_format.export_data(None)

    def test_pdf_uo_gerado_com_estrutura_valida(self):
        pdf_bytes = self._gerar_pdf(self.superuser)

        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"%%EOF", pdf_bytes)
        self.assertGreater(len(pdf_bytes), 1000)
        self.assertIn(b"/Author (777888)", pdf_bytes)

    def test_pdf_uo_sem_request_usa_sistema(self):
        pdf_bytes = self._gerar_pdf(usuario=None)

        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn(b"/Author", pdf_bytes)

    def test_resolve_usuario_exportacao_sem_request_retorna_sistema(self):
        pdf_format = UnidadeOrcamentariaPDFFormat()

        self.assertEqual(pdf_format._resolver_usuario_exportacao(None), "Sistema")

    def test_exportacao_excel_uo_com_status_legivel(self):
        resource = UnidadeOrcamentariaResource()
        dataset = resource.export(UnidadeOrcamentaria.objects.all())

        status_index = dataset.headers.index("Status")
        status_values = [row[status_index] for row in dataset]
        self.assertIn("Ativa", status_values)
        self.assertIn("Inativa", status_values)
