from django.test import TestCase
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.models import ContentType

from dados_comuns.models import (
    UnidadeAdministrativa,
    UnidadeOrcamentaria,
    HistoricoGeral,
)
from dados_comuns.admin import UnidadeAdministrativaAdmin
from dados_comuns.tests.factories import criar_ua, criar_uo


class SetupData:
    def create_instance(self):

        obj = {
            "codigo": "39684596",
            "sigla": "COTIC",
            "nome": "Centro de tecnologia",
        }
        criar_ua(**obj)

    def create_multiple_instances(self):
        uo = criar_uo(codigo="100", nome="UO 100")  # ou sem params

        instances = [
            {
                "codigo": "100",
                "sigla": "SME",
                "nome": "Secretaria Municipal de Educação",
            },
            {
                "codigo": "050",
                "sigla": "DRE-BT",
                "nome": "Diretoria Regional de Educação Butantã",
            },
            {"codigo": "200", "sigla": "COTIC", "nome": "Centro de Tecnologia"},
            {
                "codigo": "050",
                "sigla": "DRE-CS",
                "nome": "Diretoria Regional de Educação Campo Limpo",
            },
            {
                "codigo": "050",
                "sigla": "DRE-CL",
                "nome": "Diretoria Regional de Educação Capela do Socorro",
            },
        ]

        return [criar_ua(uo=uo, **obj) for obj in instances]


class UnidadeAdministrativaTestCase(TestCase):
    start = SetupData()
    entity = UnidadeAdministrativa

    def setUp(self):
        self.start.create_instance()

    def test_get(self):
        instance = self.entity.objects.first()
        self.assertIsInstance(instance, self.entity)

    def test_update(self):
        instance = self.entity.objects.first()
        instance.nome = "Mesa triunfo 2"
        instance.save()
        self.assertEqual(instance.nome, "Mesa triunfo 2")

    def test_delete(self):
        instance = self.entity.objects.first()
        instance.delete()

        self.assertFalse(instance.id)
        self.assertIsInstance(instance, self.entity)


class UnidadeAdministrativaOrderingTestCase(TestCase):

    def setUp(self):
        setup = SetupData()
        setup.create_multiple_instances()

    def test_ordering_by_codigo_sigla_nome(self):
        unidades = UnidadeAdministrativa.objects.all()

        self.assertGreater(unidades.count(), 0)

        unidades_list = list(unidades)

        self.assertEqual(unidades_list[0].codigo, "050")
        self.assertEqual(unidades_list[-1].codigo, "200")

        unidades_codigo_050 = [u for u in unidades_list if u.codigo == "050"]
        self.assertEqual(len(unidades_codigo_050), 3)
        self.assertEqual(unidades_codigo_050[0].sigla, "DRE-BT")
        self.assertEqual(unidades_codigo_050[1].sigla, "DRE-CL")
        self.assertEqual(unidades_codigo_050[2].sigla, "DRE-CS")

    def test_model_meta_ordering(self):
        self.assertEqual(
            UnidadeAdministrativa._meta.ordering, ["codigo", "sigla", "nome"]
        )

    def test_str_representation(self):
        unidade = UnidadeAdministrativa.objects.first()
        expected = f"{unidade.codigo} - {unidade.sigla}"
        self.assertEqual(str(unidade), expected)


class UnidadeAdministrativaAdminTestCase(TestCase):

    def setUp(self):
        setup = SetupData()
        uas = setup.create_multiple_instances()
        self.site = AdminSite()
        self.admin = UnidadeAdministrativaAdmin(UnidadeAdministrativa, self.site)
        self.ua = uas[0] if uas else criar_ua()

    def test_list_display_fields(self):
        expected_fields = ("codigo", "sigla", "nome", "unidade_orcamentaria", "status")
        self.assertEqual(self.admin.list_display, expected_fields)

    def test_search_fields_order(self):
        expected_fields = (
            "sigla",
            "nome",
            "codigo",
            "unidade_orcamentaria__codigo",
            "unidade_orcamentaria__nome",
        )
        self.assertEqual(self.admin.search_fields, expected_fields)

    def test_search_help_text(self):
        expected_text = "Pesquise por sigla, nome, código ou Unidade Orçamentária."
        self.assertEqual(self.admin.search_help_text, expected_text)

    def test_admin_ordering(self):
        expected_ordering = ("unidade_orcamentaria__codigo", "codigo", "sigla", "nome")
        self.assertEqual(self.admin.ordering, expected_ordering)

    def test_admin_queryset_ordering(self):
        from django.test import RequestFactory
        from usuario.models import Usuario

        factory = RequestFactory()
        request = factory.get("/admin/dados_comuns/unidadeadministrativa/")

        request.user = Usuario.objects.create_superuser(
            username="admin",
            email="admin@test.com",
            password="123",
            unidade_orcamentaria=self.ua.unidade_orcamentaria,
        )

        queryset = self.admin.get_queryset(request)
        unidades_list = list(queryset)

        self.assertGreater(len(unidades_list), 0)
        self.assertEqual(unidades_list[0].codigo, "050")
        self.assertEqual(unidades_list[-1].codigo, "200")


class UnidadeOrcamentariaTestCase(TestCase):
    """Testes para UnidadeOrcamentaria."""

    def test_str(self):
        uo = criar_uo(codigo="16", nome="SME")
        self.assertEqual(str(uo), "16 - SME")


class UnidadeAdministrativaCleanTestCase(TestCase):
    """Testes para UnidadeAdministrativa.clean e propriedades."""

    def test_clean_exige_unidade_orcamentaria(self):
        """UA sem unidade_orcamentaria levanta ValidationError no clean."""
        ua = UnidadeAdministrativa(
            codigo="001",
            sigla="UA",
            nome="Unidade",
            status=UnidadeAdministrativa.ATIVA,
            unidade_orcamentaria=None,
        )
        with self.assertRaises(ValidationError) as ctx:
            ua.clean()
        self.assertIn("unidade_orcamentaria", ctx.exception.message_dict)

    def test_is_ativa(self):
        """is_ativa True quando status ATIVA."""
        ua = criar_ua(status=UnidadeAdministrativa.ATIVA)
        self.assertTrue(ua.is_ativa)
        ua.status = UnidadeAdministrativa.INATIVA
        ua.save(update_fields=["status"])
        ua.refresh_from_db()
        self.assertFalse(ua.is_ativa)

    def test_pode_inativar_sem_bens(self):
        """pode_inativar True quando não há bens na UA."""
        ua = criar_ua(codigo="901", sigla="UA9", nome="UA 9")
        self.assertTrue(ua.pode_inativar())


class HistoricoGeralTestCase(TestCase):
    """Testes para HistoricoGeral."""

    def test_str(self):
        uo = criar_uo(codigo="99", nome="UO Teste")
        ct = ContentType.objects.get_for_model(UnidadeOrcamentaria)
        hist = HistoricoGeral.objects.create(
            content_type=ct,
            object_id=str(uo.pk),
            campo="nome",
            valor_antigo="Antigo",
            valor_novo="Novo",
        )
        self.assertIn(str(ct), str(hist))
        self.assertIn(str(uo.pk), str(hist))
        self.assertIn("nome", str(hist))
