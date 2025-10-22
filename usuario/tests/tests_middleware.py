from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.middleware import AuthenticationMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from usuario.middleware import ForcePasswordChangeMiddleware
from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY

User = get_user_model()


def get_request_with_user(path, user):
    rf = RequestFactory()
    req = rf.get(path)
    # cria sessão
    SessionMiddleware(lambda r: None).process_request(req)
    req.session.save()

    # autentica o usuário na sessão (como o Client faria)
    req.session[SESSION_KEY] = str(user.pk)
    req.session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    req.session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    req.session.save()

    # agora o AuthenticationMiddleware vai popular request.user corretamente
    AuthenticationMiddleware(lambda r: None)(req)
    return req


class ForcePasswordChangeMiddlewareTests(TestCase):
    def get_mw(self):
        return ForcePasswordChangeMiddleware(lambda req: HttpResponse("OK"))

    def test_redirects_when_must_change_password_true(self):
        u = User.objects.create_user(
            username="maria", password="x", must_change_password=True
        )
        req = get_request_with_user("/admin/", u)
        resp = self.get_mw()(req)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/password-change/?next=%2Fadmin%2F", resp["Location"])

    def test_redirects_when_session_flag_set(self):
        u = User.objects.create_user(
            username="joao", password="x", must_change_password=False
        )
        req = get_request_with_user("/admin/", u)
        req.session["force_pw_change_first_admin"] = True
        req.session.save()
        resp = self.get_mw()(req)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/password-change/?next=%2Fadmin%2F", resp["Location"])

    def test_allows_when_ok(self):
        u = User.objects.create_user(
            username="ok", password="x", must_change_password=False
        )
        req = get_request_with_user("/admin/", u)
        resp = self.get_mw()(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"OK")
