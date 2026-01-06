from rest_framework.test import APITestCase
from rest_framework import status
from usuario.models import Usuario
from django.core import mail
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError


class AuthEndpointsTestCase(APITestCase):
    def setUp(self):
        self.user = Usuario.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="testpass123",
            nome="Test User",
            rf="1234567",
            is_active=True,
        )

    def test_me_unauthenticated(self):
        me_url = "/api/auth/me/"
        resp = self.client.get(me_url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_password_reset_email_not_found(self):
        reset_url = "/api/auth/password-reset/"
        resp = self.client.post(
            reset_url, {"email": "naoexiste@example.com"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_confirm_invalid_token(self):
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        confirm_url = "/api/auth/password-reset-confirm/"
        resp = self.client.post(
            confirm_url,
            {
                "uidb64": uidb64,
                "token": "tokeninvalido",
                "new_password": "novaSenha123",
                "new_password_confirm": "novaSenha123",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_change_wrong_old_password(self):
        login_url = "/api/auth/login/"
        resp = self.client.post(
            login_url,
            {"username": "testuser", "password": "testpass123"},
            format="json",
        )
        access = resp.data["access"]
        change_url = "/api/auth/password-change/"
        resp = self.client.post(
            change_url,
            {
                "old_password": "errada",
                "new_password": "outrasenha123",
                "new_password_confirm": "outrasenha123",
            },
            HTTP_AUTHORIZATION=f"Bearer {access}",
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        url = "/api/auth/login/"
        resp = self.client.post(
            url, {"username": "testuser", "password": "testpass123"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_password_change_unauthenticated(self):
        change_url = "/api/auth/password-change/"
        resp = self.client.post(
            change_url,
            {
                "old_password": "testpass123",
                "new_password": "outrasenha123",
                "new_password_confirm": "outrasenha123",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_verify_invalid(self):
        verify_url = "/api/auth/token/verify/"
        resp = self.client.post(verify_url, {"token": "tokeninvalido"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_success(self):
        url = "/api/auth/login/"
        resp = self.client.post(
            url, {"username": "testuser", "password": "testpass123"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp.data)
        self.assertNotIn("refresh", resp.data)
        self.assertIn("refresh_token", resp.cookies)
        cookie = resp.cookies["refresh_token"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")

        self.assertIn("user", resp.data)

    def test_login_fail(self):
        url = "/api/auth/login/"
        resp = self.client.post(
            url, {"username": "testuser", "password": "wrongpass"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_authenticated(self):
        url = "/api/auth/login/"
        resp = self.client.post(
            url, {"username": "testuser", "password": "testpass123"}, format="json"
        )
        access = resp.data["access"]
        me_url = "/api/auth/me/"
        resp = self.client.get(me_url, HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["username"], "testuser")

    def test_token_refresh(self):
        login_url = "/api/auth/login/"
        resp_login = self.client.post(
            login_url,
            {"username": "testuser", "password": "testpass123"},
            format="json",
        )
        self.assertEqual(resp_login.status_code, status.HTTP_200_OK)

        refresh_token_value = resp_login.cookies["refresh_token"].value
        refresh_url = "/api/auth/token/refresh/"

        self.client.cookies["refresh_token"] = refresh_token_value
        resp_refresh = self.client.post(refresh_url, {}, format="json")

        self.assertEqual(resp_refresh.status_code, status.HTTP_200_OK)
        self.assertIn("access", resp_refresh.data)

        if settings.SIMPLE_JWT["ROTATE_REFRESH_TOKENS"]:
            self.assertIn("refresh_token", resp_refresh.cookies)
            self.assertNotEqual(resp_refresh.cookies["refresh_token"].value, "")

    def test_token_verify(self):
        login_url = "/api/auth/login/"
        resp = self.client.post(
            login_url,
            {"username": "testuser", "password": "testpass123"},
            format="json",
        )
        access = resp.data["access"]
        verify_url = "/api/auth/token/verify/"
        resp = self.client.post(verify_url, {"token": access}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_logout_success(self):
        refresh = RefreshToken.for_user(self.user)
        refresh_token_str = str(refresh)

        logout_url = "/api/auth/logout/"

        self.client.cookies["refresh_token"] = refresh_token_str

        resp = self.client.post(logout_url)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertEqual(resp.cookies["refresh_token"].value, "")

        if settings.SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"]:
            try:
                refresh.check_blacklist()
                self.fail("Token deveria estar na blacklist")
            except TokenError:
                pass

    def test_password_reset_flow(self):
        reset_url = "/api/auth/password-reset/"
        resp = self.client.post(
            reset_url, {"email": "testuser@example.com"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        # Simula confirmação
        uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        confirm_url = "/api/auth/password-reset-confirm/"
        resp = self.client.post(
            confirm_url,
            {
                "uidb64": uidb64,
                "token": token,
                "new_password": "newpass123",
                "new_password_confirm": "newpass123",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("newpass123"))

    def test_password_change_authenticated(self):
        login_url = "/api/auth/login/"
        resp = self.client.post(
            login_url,
            {"username": "testuser", "password": "testpass123"},
            format="json",
        )
        access = resp.data["access"]
        change_url = "/api/auth/password-change/"
        resp = self.client.post(
            change_url,
            {
                "old_password": "testpass123",
                "new_password": "outrasenha123",
                "new_password_confirm": "outrasenha123",
            },
            HTTP_AUTHORIZATION=f"Bearer {access}",
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("outrasenha123"))
