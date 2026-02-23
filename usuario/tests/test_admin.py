"""Testes para usuario.admin (CustomUserModelAdmin)."""
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase

from usuario.models import Usuario
from usuario.admin import CustomUserModelAdmin
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class TestCustomUserModelAdmin(TestCase):
    """Testes para CustomUserModelAdmin."""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.uo = criar_uo(codigo="401")
        self.ua = criar_ua(uo=self.uo, codigo="401", status=UnidadeAdministrativa.ATIVA)
        self.grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)

        self.superuser = Usuario.objects.create_superuser(
            username="super",
            password="x",
            email="super@test.com",
        )
        self.usuario_comum = Usuario.objects.create_user(
            username="comum",
            password="x",
            email="comum@test.com",
            nome="Comum",
            unidade_orcamentaria=self.uo,
            unidade_administrativa=self.ua,
        )
        self.usuario_comum.groups.add(self.grupo_operador)

        self.admin = CustomUserModelAdmin(Usuario, self.site)

    def test_get_grupo_gestor(self):
        """get_grupo retorna GESTOR_PATRIMONIO para gestor."""
        gestor = Usuario.objects.create_user(
            username="gestor",
            password="x",
            email="gestor@test.com",
            unidade_orcamentaria=self.uo,
            unidade_administrativa=self.ua,
        )
        gestor.groups.add(self.grupo_gestor)
        self.assertEqual(self.admin.get_grupo(gestor), "GESTOR_PATRIMONIO")

    def test_get_grupo_operador(self):
        """get_grupo retorna OPERADOR_INVENTARIO para operador."""
        self.assertEqual(self.admin.get_grupo(self.usuario_comum), "OPERADOR_INVENTARIO")

    def test_get_grupo_sem_grupo(self):
        """get_grupo retorna '-' para usuário sem grupo de perfil."""
        user = Usuario.objects.create_user(
            username="sem_grupo",
            password="x",
            email="sem@test.com",
            unidade_orcamentaria=self.uo,
        )
        self.assertEqual(self.admin.get_grupo(user), "-")

    def test_get_readonly_fields_com_obj_inclui_username(self):
        """get_readonly_fields com objeto inclui username."""
        request = self.factory.get("/")
        request.user = self.superuser
        readonly = self.admin.get_readonly_fields(request, self.usuario_comum)
        self.assertIn("username", readonly)

    def test_get_readonly_fields_sem_obj(self):
        """get_readonly_fields sem objeto retorna base."""
        request = self.factory.get("/")
        request.user = self.superuser
        readonly = self.admin.get_readonly_fields(request, None)
        self.assertEqual(readonly, self.admin.readonly_fields)

    def test_get_fieldsets_superuser_inclui_superadmin(self):
        """get_fieldsets para superuser inclui campo is_superuser."""
        request = self.factory.get("/")
        request.user = self.superuser
        fieldsets = self.admin.get_fieldsets(request, self.usuario_comum)
        nomes = [fs[0] for fs in fieldsets]
        self.assertIn("Super-admin", nomes)

    def test_get_fieldsets_nao_superuser_nao_inclui_superadmin(self):
        """get_fieldsets para não superuser não inclui Super-admin."""
        request = self.factory.get("/")
        request.user = self.usuario_comum
        fieldsets = self.admin.get_fieldsets(request, self.usuario_comum)
        nomes = [fs[0] for fs in fieldsets]
        self.assertNotIn("Super-admin", nomes)

    def test_get_add_fieldsets_superuser_inclui_superadmin(self):
        """get_add_fieldsets para superuser inclui is_superuser."""
        request = self.factory.get("/")
        request.user = self.superuser
        fieldsets = self.admin.get_add_fieldsets(request)
        nomes = [fs[0] for fs in fieldsets]
        self.assertIn("Super-admin", nomes)

    def test_formfield_for_foreignkey_unidade_orcamentaria_superuser(self):
        """formfield_for_foreignkey UO para superuser retorna todas UOs."""
        request = self.factory.get("/")
        request.user = self.superuser
        field = Usuario._meta.get_field("unidade_orcamentaria")
        result = self.admin.formfield_for_foreignkey(field, request)
        self.assertEqual(result.queryset.count(), UnidadeOrcamentaria.objects.count())

    def test_formfield_for_foreignkey_unidade_orcamentaria_nao_superuser_com_uo(self):
        """formfield_for_foreignkey UO para não superuser com UO retorna só sua UO."""
        request = self.factory.get("/")
        request.user = self.usuario_comum
        field = Usuario._meta.get_field("unidade_orcamentaria")
        result = self.admin.formfield_for_foreignkey(field, request)
        self.assertEqual(result.queryset.count(), 1)
        self.assertIn(self.uo, result.queryset)

    def test_formfield_for_foreignkey_unidade_administrativa_filtra_por_uo(self):
        """formfield_for_foreignkey UA filtra por unidade_orcamentaria da request."""
        request = self.factory.get("/", {"unidade_orcamentaria": str(self.uo.pk)})
        request.user = self.superuser
        request.method = "GET"
        field = Usuario._meta.get_field("unidade_administrativa")
        result = self.admin.formfield_for_foreignkey(field, request)
        self.assertIn(self.ua, result.queryset)

    def test_get_form_define_obj_em_request(self):
        """get_form define _obj_usuario_admin no request."""
        request = self.factory.get("/")
        request.user = self.superuser
        form_class = self.admin.get_form(request, self.usuario_comum)
        self.assertEqual(getattr(request, "_obj_usuario_admin", None), self.usuario_comum)
