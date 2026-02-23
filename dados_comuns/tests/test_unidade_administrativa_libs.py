"""Testes para dados_comuns.libs.unidade_administrativa."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from dados_comuns.libs.unidade_administrativa import uas_do_usuario


User = get_user_model()


class TestUasDoUsuario(TestCase):
    """Testes para uas_do_usuario()."""

    def setUp(self):
        self.uo = criar_uo()
        self.ua = criar_ua(uo=self.uo, status=UnidadeAdministrativa.ATIVA)
        self.ua_outra = criar_ua(uo=self.uo, status=UnidadeAdministrativa.ATIVA)

    def test_retorna_queryset_com_ua_do_usuario(self):
        """Retorna queryset com UA do usuário quando usuário tem UA."""
        user = User.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        qs = uas_do_usuario(user)
        self.assertEqual(qs.count(), 1)
        self.assertIn(self.ua, qs)

    def test_retorna_none_quando_usuario_sem_ua(self):
        """Retorna queryset vazio quando usuário não tem UA."""
        user = User.objects.create_user(
            username="user_sem_ua",
            password="x",
            email="user@test.com",
            unidade_administrativa=None,
            unidade_orcamentaria=self.uo,
        )
        qs = uas_do_usuario(user)
        self.assertEqual(qs.count(), 0)

    def test_retorna_none_quando_ua_id_none(self):
        """Retorna queryset vazio quando unidade_administrativa_id é None."""
        user = User.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=None,
            unidade_orcamentaria=self.uo,
        )
        # Simular usuário sem atributo unidade_administrativa_id
        user.unidade_administrativa_id = None
        qs = uas_do_usuario(user)
        self.assertEqual(qs.count(), 0)
