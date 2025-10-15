from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.contrib.sessions.middleware import SessionMiddleware

from usuario.signals import mark_first_admin_login

User = get_user_model()


def add_session_to_request(request):
    """Adiciona session ao RequestFactory request."""
    middleware = SessionMiddleware(lambda r: None)
    middleware.process_request(request)
    request.session.save()
    return request


class FirstLoginSignalTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_sets_session_flag_when_last_login_was_null(self):
        u = User.objects.create_user(username="bob", password="x")
        self.assertIsNone(
            User.objects.filter(pk=u.pk).values_list("last_login", flat=True).first()
        )

        request = add_session_to_request(self.factory.get("/admin/"))
        mark_first_admin_login(sender=User, user=u, request=request)

        self.assertTrue(request.session.get("force_pw_change_first_admin", False))

    def test_no_flag_when_user_already_logged_once(self):
        u = User.objects.create_user(username="bob2", password="x")
        c = self.client
        c.login(username="bob2", password="x")
        c.logout()

        self.assertIsNotNone(
            User.objects.filter(pk=u.pk).values_list("last_login", flat=True).first()
        )

        request = add_session_to_request(self.factory.get("/admin/"))
        user_logged_in.send(sender=User, request=request, user=u)
        self.assertFalse(request.session.get("force_pw_change_first_admin", False))
