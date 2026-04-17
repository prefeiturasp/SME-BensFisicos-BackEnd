from dados_comuns.tests.auth_test_utils import (
    NEW_PASSWORD1_KEY,
    NEW_PASSWORD2_KEY,
    auth_kwargs,
)
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
import uuid
from rest_framework.test import APIClient, APITestCase

from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO

User = get_user_model()


class PasswordChangeViewTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", **auth_kwargs("a123456"), must_change_password=False
        )
        self.staff = User.objects.create_user(
            username="admin1",
            **auth_kwargs("a123456"),
            is_staff=True,
            must_change_password=False,
        )

    def test_get_own_password_change_page(self):
        self.client.login(username="alice", **auth_kwargs("a123456"))
        url = reverse("password_change")

        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin/password_change.html")

    def test_post_own_password_change_sets_flags_and_redirects_next(self):
        self.client.login(username="alice", **auth_kwargs("a123456"))
        next_url = "/admin/"

        url = f'{reverse("password_change")}?next={next_url}'

        resp = self.client.post(
            url,
            {
                NEW_PASSWORD1_KEY: "N0va@s3nhA!",
                NEW_PASSWORD2_KEY: "N0va@s3nhA!",
                "next": next_url,
            },
            follow=False,
        )

        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].endswith(next_url))

        u = User.objects.get(pk=self.user.pk)

        self.assertFalse(u.must_change_password)
        self.assertIsNotNone(u.last_password_change)
        self.assertLessEqual(u.last_password_change, timezone.now())
        self.assertTrue(self.client.login(username="alice", **auth_kwargs("N0va@s3nhA!")))

    def test_staff_changes_other_user_password_without_old_password(self):
        self.client.login(username="admin1", **auth_kwargs("a123456"))
        target = self.user

        next_url = f"/admin/usuario/usuario/{target.pk}/change/"

        url = f'{reverse("password_change")}?user_id={target.pk}&next={next_url}'

        resp = self.client.post(
            url,
            {
                NEW_PASSWORD1_KEY: "Sup3rS3nh@",
                NEW_PASSWORD2_KEY: "Sup3rS3nh@",
                "user_id": str(target.pk),
                "next": next_url,
            },
            follow=False,
        )

        self.assertEqual(resp.status_code, 302)

        self.assertTrue(resp["Location"].endswith(next_url))

        target.refresh_from_db()

        self.assertFalse(target.must_change_password)
        self.assertIsNotNone(target.last_password_change)
        self.assertTrue(self.client.login(username="alice", **auth_kwargs("Sup3rS3nh@")))

    def test_redirecionamento_admin_senha_exige_autenticacao(self):
        url = reverse("admin_usuario_password_redirect", args=[self.user.pk])
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp["Location"])
        self.assertIn("next=", resp["Location"])

    def test_redirecionamento_admin_senha_nega_usuario_nao_staff(self):
        self.client.login(username="alice", **auth_kwargs("a123456"))
        url = reverse("admin_usuario_password_redirect", args=[self.user.pk])
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 403)

    def test_redirecionamento_admin_senha_permite_staff_via_get(self):
        self.client.login(username="admin1", **auth_kwargs("a123456"))
        url = reverse("admin_usuario_password_redirect", args=[self.user.pk])
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("password_change"), resp["Location"])
        self.assertIn(f"user_id={self.user.pk}", resp["Location"])

    def test_redirecionamento_admin_senha_rejeita_post(self):
        self.client.login(username="admin1", **auth_kwargs("a123456"))
        url = reverse("admin_usuario_password_redirect", args=[self.user.pk])
        resp = self.client.post(url)

        self.assertEqual(resp.status_code, 405)


class AdminLoginViewTests(TestCase):

    def setUp(self):
        self.senha_list = ["S3nh", "@", "123"]
        self.senha = "".join(self.senha_list)
        self.user = User.objects.create_user(username="bob", password=self.senha)

    def test_login_redirects_selecionar_ua(self):

        resp = self.client.post(
            "/admin/login/",
            {
                "username": "bob",
                "password": self.senha,
            },
            follow=False,
        )

        self.assertEqual(resp.status_code, 302)

        self.assertEqual(resp["Location"], reverse("selecionar_ua"))

    def test_login_redirects_selecionar_ua_preserving_next(self):

        resp = self.client.post(
            "/admin/login/",
            {
                "username": "bob",
                "password": self.senha,
                "next": "/admin/",
            },
            follow=False,
        )

        self.assertEqual(resp.status_code, 302)

        self.assertIn(reverse("selecionar_ua"), resp["Location"])
        self.assertIn("next=%2Fadmin%2F", resp["Location"])


class AdminGoogleAnalyticsTests(TestCase):

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="analytics_admin",
            **auth_kwargs("analytics-admin-123"),
            is_staff=True,
            is_superuser=True,
            must_change_password=False,
        )

    def test_admin_login_exibe_google_analytics_em_producao(self):
        with self.settings(DEBUG=False):
            response = self.client.get(reverse("admin:login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f"https://www.googletagmanager.com/gtag/js?id={settings.GOOGLE_ANALYTICS_ID}",
        )
        self.assertContains(
            response,
            f"gtag('config', '{settings.GOOGLE_ANALYTICS_ID}');",
            html=False,
        )

    def test_admin_login_nao_exibe_google_analytics_em_desenvolvimento(self):
        with self.settings(DEBUG=True):
            response = self.client.get(reverse("admin:login"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "www.googletagmanager.com/gtag/js")
        self.assertNotContains(response, "gtag('config'")

    def test_admin_index_exibe_google_analytics_em_producao(self):
        self.client.force_login(self.staff_user)

        with self.settings(DEBUG=False):
            response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f"https://www.googletagmanager.com/gtag/js?id={settings.GOOGLE_ANALYTICS_ID}",
        )
        self.assertContains(
            response,
            f"gtag('config', '{settings.GOOGLE_ANALYTICS_ID}');",
            html=False,
        )


class SelecionarUAViewTests(TestCase):

    def setUp(self):

        self.senha_list = ["S3nh", "@", "123"]
        self.senha = "".join(self.senha_list)

        self.ua1 = criar_ua(codigo="001", sigla="UA1", nome="Unidade 1")

        self.ua2 = criar_ua(
            uo=self.ua1.unidade_orcamentaria,
            codigo="002",
            sigla="UA2",
            nome="Unidade 2",
        )

        self.grupo_gestor = Group.objects.get_or_create(
            name=GRUPO_GESTOR_PATRIMONIO
        )[0]

        self.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

        self.gestor = User.objects.create_user(
            username="gestor1",
            password=self.senha,
            unidade_orcamentaria=self.ua1.unidade_orcamentaria,
            unidade_administrativa=self.ua1,
            is_staff=True,
            must_change_password=False,
        )

        self.gestor.groups.add(self.grupo_gestor)

        self.operador = User.objects.create_user(
            username="operador1",
            password=self.senha,
            unidade_orcamentaria=self.ua1.unidade_orcamentaria,
            unidade_administrativa=self.ua1,
            is_staff=True,
            must_change_password=False,
        )

        self.operador.groups.add(self.grupo_operador)

        self.operador.unidades_administrativas.add(self.ua1, self.ua2)

    def test_gestor_ve_opcao_visao_geral_no_select(self):

        self.client.login(username="gestor1", password=self.senha)

        resp = self.client.get(reverse("selecionar_ua"))

        self.assertEqual(resp.status_code, 200)

        self.assertContains(resp, "visão geral")
        self.assertContains(resp, "__UO__")

    def test_gestor_pode_selecionar_visao_geral(self):

        self.client.login(username="gestor1", password=self.senha)

        resp = self.client.post(
            reverse("selecionar_ua"),
            {
                "unidade_administrativa": "__UO__",
                "next": "/admin/",
            },
            follow=False,
        )

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp["Location"], "/admin/")

        self.gestor.refresh_from_db()

        self.assertIsNone(self.gestor.unidade_administrativa_id)

        self.assertEqual(
            self.gestor.unidade_orcamentaria_id,
            self.ua1.unidade_orcamentaria_id,
        )

    def test_operador_nao_ve_opcao_visao_geral(self):

        self.client.login(username="operador1", password=self.senha)

        resp = self.client.get(reverse("selecionar_ua"))

        self.assertEqual(resp.status_code, 200)

        self.assertNotContains(resp, "__UO__")


class UsuarioViewSetTests(TestCase):

    def setUp(self):

        self.senha_list = ["S3nh", "@", "123"]
        self.senha = "".join(self.senha_list)

        self.client = APIClient()

        self.admin = User.objects.create_user(
            username="admin",
            password=self.senha,
            is_staff=True,
            is_superuser=True,
        )

        self.user = User.objects.create_user(
            username="user1",
            email="user@test.com",
            password=self.senha,
        )

        self.client.login(username="admin", password=self.senha)

        self.client.force_authenticate(user=self.admin)

        self.list_url = reverse("usuario-list")

        self.detail_url = reverse("usuario-detail", args=[self.user.id])

        self.restore_url = reverse("usuario-restore", args=[self.user.id])

    def test_list_users(self):

        resp = self.client.get(self.list_url)

        self.assertEqual(resp.status_code, 200)

        self.assertIn("results", resp.data)

    def test_retrieve_user(self):

        resp = self.client.get(self.detail_url)

        self.assertEqual(resp.status_code, 200)

        self.assertEqual(resp.data["username"], "user1")

    def test_create_user(self):

        resp = self.client.post(
            self.list_url,
            {
                "username": "novo",
                "email": "novo@test.com",
                "password": self.senha,
                "password_confirm": self.senha,
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 201)

        self.assertTrue(User.objects.filter(username="novo").exists())

        user = User.objects.get(username="novo")

        self.assertTrue(user.must_change_password)
        self.assertIsNotNone(user.last_password_change)

    def test_update_user(self):

        resp = self.client.put(
            self.detail_url,
            {
                "username": "user1",
                "email": "novo@email.com",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)

        self.user.refresh_from_db()

        self.assertEqual(self.user.email, "novo@email.com")

    def test_partial_update_user(self):

        resp = self.client.patch(
            self.detail_url,
            {
                "email": "patch@email.com",
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 200)

        self.user.refresh_from_db()

        self.assertEqual(self.user.email, "patch@email.com")

    def test_soft_delete_user(self):

        resp = self.client.delete(self.detail_url)

        self.assertEqual(resp.status_code, 200)

        self.user.refresh_from_db()

        self.assertFalse(self.user.is_active)

    def test_restore_user(self):

        self.user.is_active = False
        self.user.save()

        resp = self.client.post(self.restore_url)

        self.assertEqual(resp.status_code, 200)

        self.user.refresh_from_db()

        self.assertTrue(self.user.is_active)

    def test_filter_active_users(self):

        self.user.is_active = False
        self.user.save()

        resp = self.client.get(self.list_url, {"is_active": False})

        self.assertEqual(resp.status_code, 200)

        usernames = [u["username"] for u in resp.data["results"]]

        self.assertIn("user1", usernames)


# =========================================
# TESTES NEGATIVOS DE SEGURANÇA (AUDITORIA)
# =========================================

class UsuarioPermissionNegativeTests(APITestCase):

    def setUp(self):

        self.senha_list = ["S3nh", "@", "123"]
        self.senha = "".join(self.senha_list)

        self.client = APIClient()

        self.grupo_gestor = Group.objects.get_or_create(
            name=GRUPO_GESTOR_PATRIMONIO
        )[0]

        self.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

        self.ua1 = criar_ua(codigo="001", sigla="UA1", nome="Unidade 1")

        self.ua2 = criar_ua(
            uo=self.ua1.unidade_orcamentaria,
            codigo="002",
            sigla="UA2",
            nome="Unidade 2",
        )

        self.gestor = User.objects.create_user(
            username="gestor",
            password=self.senha,
            unidade_orcamentaria=self.ua1.unidade_orcamentaria,
            unidade_administrativa=self.ua1,
            is_staff=True,
        )

        self.gestor.groups.add(self.grupo_gestor)

        self.operador = User.objects.create_user(
            username="operador",
            password=self.senha,
            unidade_orcamentaria=self.ua1.unidade_orcamentaria,
            unidade_administrativa=self.ua1,
            is_staff=True,
        )

        self.operador.groups.add(self.grupo_operador)

        self.target_user = User.objects.create_user(
            username="target",
            password=self.senha,
            unidade_orcamentaria=self.ua1.unidade_orcamentaria,
            unidade_administrativa=self.ua1,
        )

        self.list_url = reverse("usuario-list")
        self.detail_url = reverse("usuario-detail", args=[self.target_user.id])

    def test_operador_nao_pode_criar_usuario(self):

        self.client.force_authenticate(user=self.operador)

        resp = self.client.post(
            self.list_url,
            {
                "username": "hack",
                "password": self.senha,
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 403)

    def test_operador_nao_pode_editar_usuario(self):

        self.client.force_authenticate(user=self.operador)

        resp = self.client.patch(
            self.detail_url,
            {
                "email": "hack@test.com"
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 403)

    def test_nao_permitir_elevar_para_superuser(self):

        self.client.force_authenticate(user=self.operador)

        resp = self.client.patch(
            self.detail_url,
            {
                "is_superuser": True
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 403)

    def test_nao_permitir_elevar_para_staff(self):

        self.client.force_authenticate(user=self.operador)

        resp = self.client.patch(
            self.detail_url,
            {
                "is_staff": True
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 403)

    def test_nao_permitir_alterar_grupos(self):

        gestor_group = Group.objects.get(name=GRUPO_GESTOR_PATRIMONIO)

        self.client.force_authenticate(user=self.operador)

        resp = self.client.patch(
            self.detail_url,
            {
                "groups": [gestor_group.id]
            },
            format="json",
        )

        self.assertEqual(resp.status_code, 403)

    def test_acesso_fora_do_escopo_uo(self):

        uo_externa = criar_uo(
            codigo="998",
            sigla="UOEXT",
            nome="UO Externa"
        )

        ua_externa = criar_ua(
            codigo="999",
            sigla="EXT",
            nome="Externa",
            uo=uo_externa
        )

        user_externo = User.objects.create_user(
            username="externo",
            password=self.senha,
            unidade_orcamentaria=uo_externa,
            unidade_administrativa=ua_externa,
        )

        self.client.force_authenticate(user=self.operador)

        url = reverse("usuario-detail", args=[user_externo.id])

        resp = self.client.get(url)

        self.assertIn(resp.status_code, [403, 404])

    def test_gestor_nao_pode_definir_superuser(self):

        self.client.force_authenticate(user=self.gestor)

        resp = self.client.patch(
            self.detail_url,
            {
                "is_superuser": True
            },
            format="json",
        )

        self.assertIn(resp.status_code, [400, 403])

    def test_gestor_nao_pode_criar_superuser(self):

        self.client.force_authenticate(user=self.gestor)

        resp = self.client.post(
            self.list_url,
            {
                "username": "superhack",
                "password": self.senha,
                "password_confirm": self.senha,
                "is_superuser": True,
            },
            format="json",
        )

        self.assertIn(resp.status_code, [400, 403])

    def test_gestor_nao_pode_definir_staff(self):

        self.client.force_authenticate(user=self.gestor)

        resp = self.client.patch(
            self.detail_url,
            {
                "is_staff": True
            },
            format="json",
        )

        self.assertIn(resp.status_code, [400, 403])

    def test_usuario_nao_pode_alterar_proprio_grupo(self):

        self.client.force_authenticate(user=self.gestor)

        gestor_group = Group.objects.get(name=GRUPO_GESTOR_PATRIMONIO)

        url = reverse("usuario-detail", args=[self.gestor.id])

        resp = self.client.patch(
            url,
            {
                "groups": [gestor_group.id]
            },
            format="json",
        )

        self.assertIn(resp.status_code, [400, 403])
