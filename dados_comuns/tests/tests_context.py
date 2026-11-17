from django.contrib.auth.models import AnonymousUser
from django.test import SimpleTestCase

from dados_comuns.context import audit_as, get_user, set_user

USUARIO = object()


class ContextoAuditoriaTestCase(SimpleTestCase):
    def tearDown(self):
        set_user(None)

    def test_get_user_retorna_usuario_definido(self):
        set_user(USUARIO)

        self.assertIs(get_user(), USUARIO)

    def test_get_user_ignora_anonymous_user(self):
        set_user(AnonymousUser())

        self.assertIsNone(get_user())

    def test_audit_as_restaura_usuario_anterior(self):
        set_user(None)

        with audit_as(USUARIO):
            self.assertIs(get_user(), USUARIO)

        self.assertIsNone(get_user())
