from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.utils import timezone
from dados_comuns.tests.factories import criar_ua
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO

User = get_user_model()


class PasswordChangeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="a123456")
        self.staff = User.objects.create_user(
            username="admin1", password="a123456", is_staff=True
        )

    def test_get_own_password_change_page(self):
        self.client.login(username="alice", password="a123456")
        url = reverse("password_change")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "admin/password_change.html")

    def test_post_own_password_change_sets_flags_and_redirects_next(self):
        self.client.login(username="alice", password="a123456")
        next_url = "/admin/"
        url = f'{reverse("password_change")}?next={next_url}'
        resp = self.client.post(
            url,
            {
                "new_password1": "N0va@s3nhA!",
                "new_password2": "N0va@s3nhA!",
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
        self.assertTrue(self.client.login(username="alice", password="N0va@s3nhA!"))

    def test_staff_changes_other_user_password_without_old_password(self):
        self.client.login(username="admin1", password="a123456")
        target = self.user
        next_url = f"/admin/usuario/usuario/{target.pk}/change/"
        url = f'{reverse("password_change")}?user_id={target.pk}&next={next_url}'
        resp = self.client.post(
            url,
            {
                "new_password1": "Sup3rS3nh@",
                "new_password2": "Sup3rS3nh@",
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
        self.assertTrue(self.client.login(username="alice", password="Sup3rS3nh@"))


class AdminLoginViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bob", password="b123456")

    def test_login_redirects_selecionar_ua(self):
        resp = self.client.post(
            "/admin/login/",
            {
                "username": "bob",
                "password": "b123456",
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
                "password": "b123456",
                "next": "/admin/",
            },
            follow=False,
        )

        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("selecionar_ua"), resp["Location"])
        self.assertIn("next=%2Fadmin%2F", resp["Location"])


class SelecionarUAViewTests(TestCase):
    def setUp(self):
        self.ua1 = criar_ua(codigo="001", sigla="UA1", nome="Unidade 1")
        self.ua2 = criar_ua(
            uo=self.ua1.unidade_orcamentaria,
            codigo="002",
            sigla="UA2",
            nome="Unidade 2",
        )

        self.grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        self.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

        self.gestor = User.objects.create_user(
            username="gestor1",
            password="senha123",
            unidade_orcamentaria=self.ua1.unidade_orcamentaria,
            unidade_administrativa=self.ua1,
            is_staff=True,
            must_change_password=False,
        )
        self.gestor.groups.add(self.grupo_gestor)

        self.operador = User.objects.create_user(
            username="operador1",
            password="senha123",
            unidade_orcamentaria=self.ua1.unidade_orcamentaria,
            unidade_administrativa=self.ua1,
            is_staff=True,
            must_change_password=False,
        )
        self.operador.groups.add(self.grupo_operador)
        self.operador.unidades_administrativas.add(self.ua1, self.ua2)

    def test_gestor_ve_opcao_visao_geral_no_select(self):
        self.client.login(username="gestor1", password="senha123")
        resp = self.client.get(reverse("selecionar_ua"))

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "visão geral")
        self.assertContains(resp, "__UO__")

    def test_gestor_pode_selecionar_visao_geral(self):
        self.client.login(username="gestor1", password="senha123")
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
            self.gestor.unidade_orcamentaria_id, self.ua1.unidade_orcamentaria_id
        )

    def test_operador_nao_ve_opcao_visao_geral(self):
        self.client.login(username="operador1", password="senha123")
        resp = self.client.get(reverse("selecionar_ua"))

        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "__UO__")
