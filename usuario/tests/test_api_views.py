"""Testes para usuario.api_views (views e helpers)."""
from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APITestCase, APIRequestFactory
from rest_framework import status
from rest_framework.response import Response

from usuario.api_views import (
    set_refresh_token_cookie,
    LogoutAPIView,
    UserProfileAPIView,
)
from usuario.models import Usuario
from dados_comuns.tests.factories import criar_ua, criar_uo


class TestSetRefreshTokenCookie(TestCase):
    """Testes para set_refresh_token_cookie."""

    def test_set_cookie_httponly_e_samesite(self):
        response = Response()
        set_refresh_token_cookie(response, "fake-refresh-token")
        self.assertIn("refresh_token", response.cookies)
        cookie = response.cookies["refresh_token"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie.value, "fake-refresh-token")


class TestLogoutAPIView(APITestCase):
    """Testes para LogoutAPIView."""

    def test_post_sem_cookie_retorna_200_e_deleta_cookie(self):
        factory = APIRequestFactory()
        request = factory.post("/api/auth/logout/")
        view = LogoutAPIView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Logout realizado com sucesso.")
        self.assertEqual(response.cookies.get("refresh_token").value, "")

    def test_post_com_cookie_invalido_retorna_200(self):
        factory = APIRequestFactory()
        request = factory.post("/api/auth/logout/")
        request.COOKIES["refresh_token"] = "token-invalido"
        view = LogoutAPIView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response.delete_cookie("refresh_token")


class TestUserProfileAPIView(APITestCase):
    """Testes para UserProfileAPIView (get_object)."""

    def setUp(self):
        self.uo = criar_uo(codigo="801")
        self.ua = criar_ua(uo=self.uo, codigo="801", nome="UA")
        self.user = Usuario.objects.create_user(
            username="profile_user",
            password="x",
            email="p@test.com",
            nome="Profile User",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )

    def test_get_object_retorna_request_user(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["username"], "profile_user")
        self.assertEqual(resp.data["nome"], "Profile User")
