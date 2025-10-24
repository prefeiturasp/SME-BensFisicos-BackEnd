from django.test import TestCase
from django.contrib.admin.sites import AdminSite
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.admin import UnidadeAdministrativaAdmin


class SetupData:
    def create_instance(self):

        obj = {
            "codigo": "39684596",
            "sigla": "COTIC",
            "nome": "Centro de tecnologia",
        }
        UnidadeAdministrativa.objects.create(**obj)

    def create_multiple_instances(self):
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
        for obj in instances:
            UnidadeAdministrativa.objects.create(**obj)


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
        setup.create_multiple_instances()
        self.site = AdminSite()
        self.admin = UnidadeAdministrativaAdmin(UnidadeAdministrativa, self.site)

    def test_list_display_fields(self):
        expected_fields = ("codigo", "sigla", "nome")
        self.assertEqual(self.admin.list_display, expected_fields)

    def test_search_fields_order(self):
        expected_fields = ("sigla", "nome", "codigo")
        self.assertEqual(self.admin.search_fields, expected_fields)

    def test_search_help_text(self):
        expected_text = "Pesquise por sigla, nome ou código."
        self.assertEqual(self.admin.search_help_text, expected_text)

    def test_admin_ordering(self):
        expected_ordering = ("codigo", "sigla", "nome")
        self.assertEqual(self.admin.ordering, expected_ordering)

    def test_admin_queryset_ordering(self):
        from django.test import RequestFactory
        from usuario.models import Usuario

        factory = RequestFactory()
        request = factory.get("/admin/dados_comuns/unidadeadministrativa/")
        request.user = Usuario()

        queryset = self.admin.get_queryset(request)
        unidades_list = list(queryset)

        self.assertGreater(len(unidades_list), 0)
        self.assertEqual(unidades_list[0].codigo, "050")
        self.assertEqual(unidades_list[-1].codigo, "200")
