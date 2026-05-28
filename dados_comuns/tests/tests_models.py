from datetime import date

from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua, codigo_uo
from django.test import TestCase
from django.test import RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria
from dados_comuns.admin import UnidadeAdministrativaAdmin, UnidadeOrcamentariaAdmin
from dados_comuns.formats import UnidadeOrcamentariaPDFFormat
from dados_comuns.tests.factories import criar_ua, criar_uo
from dados_comuns.utils import (
    PREFIXO_CODIGO_UO_SME,
    garantir_ua_ponto_central_externa,
)
from inventario.models import ParametroConciliacaoAnual
from usuario.models import Usuario


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
            **auth_kwargs("123"),
            unidade_orcamentaria=self.ua.unidade_orcamentaria,
        )

        queryset = self.admin.get_queryset(request)
        unidades_list = list(queryset)

        self.assertGreater(len(unidades_list), 0)
        self.assertEqual(unidades_list[0].codigo, "050")
        self.assertEqual(unidades_list[-1].codigo, "200")


class UnidadeOrcamentariaModelTestCase(TestCase):

    def test_listar_vinculos_para_exclusao_sem_vinculos(self):
        uo = criar_uo(codigo=codigo_uo(11, 11, 11), nome="UO Livre", sigla="LIV")

        self.assertEqual(uo.listar_vinculos_para_exclusao(), [])
        self.assertTrue(uo.pode_excluir())

    def test_listar_vinculos_para_exclusao_com_ua_usuario_e_parametro(self):
        uo = criar_uo(codigo=codigo_uo(22, 22, 22), nome="UO Vinculada", sigla="VIN")
        criar_ua(
            uo=uo,
            codigo=codigo_ua(22, 22, 22, 1),
            sigla="UA22",
            nome="UA Vinculada",
        )
        Usuario.objects.create_user(
            username="usuario_uo_vinculada",
            email="usuario.uo.vinculada@test.com",
            **auth_kwargs("123456"),
            nome="Usuário Vinculado",
            unidade_orcamentaria=uo,
        )
        ParametroConciliacaoAnual.objects.create(
            unidade_orcamentaria=uo,
            ano_referencia=2030,
            periodo_inicial=date(2030, 1, 1),
            periodo_final=date(2030, 3, 31),
            ativo=True,
        )

        vinculos = uo.listar_vinculos_para_exclusao()

        self.assertIn("unidades administrativas", vinculos)
        self.assertIn("usuários", vinculos)
        self.assertIn("parâmetros de conciliação anual", vinculos)
        self.assertFalse(uo.pode_excluir())


class UnidadeOrcamentariaAdminTestCase(TestCase):

    def setUp(self):
        self.site = AdminSite()
        self.admin = UnidadeOrcamentariaAdmin(UnidadeOrcamentaria, self.site)
        self.factory = RequestFactory()
        self.superuser = Usuario.objects.create_superuser(
            username="admin_uo",
            email="admin.uo@test.com",
            **auth_kwargs("123"),
        )
        self.gestor = Usuario.objects.create_user(
            username="gestor_uo_admin",
            email="gestor.uo.admin@test.com",
            **auth_kwargs("123"),
            is_staff=True,
        )

    def _request_com_messages(self, path="/admin/dados_comuns/unidadeorcamentaria/add/"):
        request = self.factory.post(path)
        request.user = self.superuser
        setattr(request, "session", "session")
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_permissoes_admin_somente_superuser(self):
        request_super = self.factory.get("/admin/dados_comuns/unidadeorcamentaria/")
        request_super.user = self.superuser

        request_gestor = self.factory.get("/admin/dados_comuns/unidadeorcamentaria/")
        request_gestor.user = self.gestor

        self.assertTrue(self.admin.has_module_permission(request_super))
        self.assertTrue(self.admin.has_view_permission(request_super))
        self.assertTrue(self.admin.has_add_permission(request_super))
        self.assertTrue(self.admin.has_change_permission(request_super))
        self.assertFalse(self.admin.has_delete_permission(request_super))
        self.assertTrue(self.admin.has_export_permission(request_super))

        self.assertFalse(self.admin.has_module_permission(request_gestor))
        self.assertFalse(self.admin.has_view_permission(request_gestor))
        self.assertFalse(self.admin.has_add_permission(request_gestor))
        self.assertFalse(self.admin.has_change_permission(request_gestor))
        self.assertFalse(self.admin.has_export_permission(request_gestor))

    def test_form_admin_exige_codigo_e_nome_mas_nao_sigla(self):
        request = self.factory.get("/admin/dados_comuns/unidadeorcamentaria/add/")
        request.user = self.superuser

        form_class = self.admin.get_form(request)

        form_sem_sigla = form_class(
            data={
                "codigo": codigo_uo(33, 33, 33),
                "nome": "UO Admin",
                "sigla": "",
                "ativa": True,
            }
        )
        self.assertTrue(form_sem_sigla.is_valid())

        form_sem_codigo = form_class(
            data={
                "codigo": "",
                "nome": "UO Admin",
                "sigla": "ADM",
                "ativa": True,
            }
        )
        self.assertFalse(form_sem_codigo.is_valid())
        self.assertIn("codigo", form_sem_codigo.errors)

        form_sem_nome = form_class(
            data={
                "codigo": codigo_uo(44, 44, 44),
                "nome": "",
                "sigla": "ADM",
                "ativa": True,
            }
        )
        self.assertFalse(form_sem_nome.is_valid())
        self.assertIn("nome", form_sem_nome.errors)

    def test_form_admin_aceita_campos_novos_e_valida_codigo_orgao(self):
        request = self.factory.get("/admin/dados_comuns/unidadeorcamentaria/add/")
        request.user = self.superuser

        form_class = self.admin.get_form(request)

        form_valido = form_class(
            data={
                "codigo": codigo_uo(55, 55, 55),
                "nome": "UO com órgão",
                "sigla": "ORG",
                "sigla_orgao": "PMSP",
                "orgao": "Secretaria Externa",
                "codigo_orgao": "12.34",
                "ativa": True,
            }
        )

        self.assertTrue(form_valido.is_valid(), form_valido.errors)

        form_invalido = form_class(
            data={
                "codigo": codigo_uo(56, 56, 56),
                "nome": "UO inválida",
                "sigla": "INV",
                "sigla_orgao": "INVORG",
                "orgao": "Secretaria Externa",
                "codigo_orgao": "1234",
                "ativa": True,
            }
        )

        self.assertFalse(form_invalido.is_valid())
        self.assertIn("codigo_orgao", form_invalido.errors)

    def test_model_permite_campos_novos_em_branco_para_legado(self):
        uo = criar_uo(codigo=codigo_uo(57, 57, 57), nome="UO Legado")

        self.assertEqual(uo.sigla_orgao, "")
        self.assertEqual(uo.orgao, "")
        self.assertEqual(uo.codigo_orgao, "")

    def test_admin_uo_expoe_campo_sigla_orgao_no_cadastro(self):
        self.assertIn("sigla_orgao", self.admin.fields)

    def test_admin_uo_ordena_e_renomeia_campos_de_orgao(self):
        request = self.factory.get("/admin/dados_comuns/unidadeorcamentaria/add/")
        request.user = self.superuser

        form_class = self.admin.get_form(request)

        self.assertEqual(
            list(form_class.base_fields)[3:6],
            ["codigo_orgao", "sigla_orgao", "orgao"],
        )
        self.assertEqual(
            form_class.base_fields["codigo_orgao"].label,
            "Código do Órgão",
        )
        self.assertEqual(
            form_class.base_fields["sigla_orgao"].label,
            "Sigla do Órgão",
        )
        self.assertEqual(
            form_class.base_fields["orgao"].label,
            "Nome do Órgão",
        )

    def test_admin_uo_inclui_exportacao_pdf(self):
        formatos = self.admin.get_export_formats()

        self.assertIn(UnidadeOrcamentariaPDFFormat, formatos)

    def test_save_model_cria_ua_001_para_uo_externa(self):
        request = self._request_com_messages()
        uo = UnidadeOrcamentaria(
            codigo=codigo_uo(57, 57, 57),
            nome="UO Externa",
            sigla="EXT",
            sigla_orgao="PMSP",
            orgao="Órgão externo",
            codigo_orgao="11.22",
            ativa=True,
        )

        form_class = self.admin.get_form(request)
        form = form_class(
            data={
                "codigo": uo.codigo,
                "nome": uo.nome,
                "sigla": uo.sigla,
                "sigla_orgao": uo.sigla_orgao,
                "orgao": uo.orgao,
                "codigo_orgao": uo.codigo_orgao,
                "ativa": True,
            },
            instance=uo,
        )

        self.assertTrue(form.is_valid(), form.errors)

        self.admin.save_model(request, uo, form, change=False)

        ua = UnidadeAdministrativa.objects.get(
            unidade_orcamentaria=uo,
            codigo=f"{uo.codigo}.001",
        )
        self.assertEqual(ua.nome, "Ponto Central")
        self.assertEqual(ua.sigla, "PC")

    def test_save_model_nao_cria_ua_001_para_uo_sme(self):
        request = self._request_com_messages()
        uo = UnidadeOrcamentaria(
            codigo=f"{PREFIXO_CODIGO_UO_SME}.99",
            nome="SME",
            sigla="SME",
            sigla_orgao="PMSP",
            orgao="Órgão SME",
            codigo_orgao="01.16",
            ativa=True,
        )

        form_class = self.admin.get_form(request)
        form = form_class(
            data={
                "codigo": uo.codigo,
                "nome": uo.nome,
                "sigla": uo.sigla,
                "sigla_orgao": uo.sigla_orgao,
                "orgao": uo.orgao,
                "codigo_orgao": uo.codigo_orgao,
                "ativa": True,
            },
            instance=uo,
        )

        self.assertTrue(form.is_valid(), form.errors)

        self.admin.save_model(request, uo, form, change=False)

        self.assertFalse(
            UnidadeAdministrativa.objects.filter(
                unidade_orcamentaria=uo,
                codigo=f"{uo.codigo}.001",
            ).exists()
        )

    def test_helper_normaliza_ua_001_existente_em_uo_externa(self):
        uo = criar_uo(
            codigo=codigo_uo(58, 58, 58),
            nome="UO Externa Existente",
            sigla="EXT58",
            sigla_orgao="ORG58",
            orgao="Orgao 58",
            codigo_orgao="58.58",
        )
        ua = UnidadeAdministrativa.objects.create(
            unidade_orcamentaria=uo,
            codigo="001",
            sigla="",
            nome="",
            status=UnidadeAdministrativa.ATIVA,
        )

        ua_atualizada, criada = garantir_ua_ponto_central_externa(uo)

        ua.refresh_from_db()
        self.assertFalse(criada)
        self.assertEqual(ua_atualizada.pk, ua.pk)
        self.assertEqual(ua.codigo, f"{uo.codigo}.001")
        self.assertEqual(ua.sigla, "PC")
        self.assertEqual(ua.nome, "Ponto Central")
