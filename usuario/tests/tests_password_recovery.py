from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator

User = get_user_model()


class PasswordRecoveryTests(TestCase):

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="oldpassword123"
        )
        self.user.is_active = True
        self.user.save()

    def test_password_recovery_request_page_loads(self):
        response = self.client.get(reverse("password_recovery"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Esqueceu sua senha?")

    def test_password_recovery_email_sent_for_valid_email(self):
        mail.outbox.clear()

        response = self.client.post(
            reverse("password_recovery"), {"email": "test@example.com"}
        )

        self.assertRedirects(response, reverse("password_recovery_done"))

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Redefinição de senha", mail.outbox[0].subject)
        self.assertIn("test@example.com", mail.outbox[0].to)

    def test_password_recovery_no_email_for_inactive_user(self):
        self.user.is_active = False
        self.user.save()

        response = self.client.post(
            reverse("password_recovery"), {"email": "test@example.com"}
        )

        self.assertRedirects(response, reverse("password_recovery_done"))

        self.assertEqual(len(mail.outbox), 0)

    def test_password_recovery_no_email_for_nonexistent_user(self):
        response = self.client.post(
            reverse("password_recovery"), {"email": "nonexistent@example.com"}
        )

        self.assertRedirects(response, reverse("password_recovery_done"))

        self.assertEqual(len(mail.outbox), 0)

    def test_password_recovery_confirm_page_with_valid_token(self):
        token = default_token_generator.make_token(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))

        response = self.client.get(
            reverse(
                "password_recovery_confirm", kwargs={"uidb64": uid, "token": token}
            ),
            follow=True,  # Segue redirecionamento para set-password
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Crie uma nova senha")

    def test_password_recovery_confirm_with_invalid_token(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))

        response = self.client.get(
            reverse(
                "password_recovery_confirm",
                kwargs={"uidb64": uid, "token": "invalid-token"},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Link inválido ou expirado")

    def test_password_recovery_complete_flow(self):
        mail.outbox.clear()

        response = self.client.post(
            reverse("password_recovery"), {"email": "test@example.com"}
        )
        self.assertRedirects(response, reverse("password_recovery_done"))

        self.assertEqual(len(mail.outbox), 1)

        token = default_token_generator.make_token(self.user)
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))

        confirm_url = reverse(
            "password_recovery_confirm", kwargs={"uidb64": uid, "token": token}
        )

        response = self.client.post(
            confirm_url,
            {
                "new_password1": "newpassword123!",
                "new_password2": "newpassword123!",
            },
        )

        if response.status_code == 302:
            set_password_url = response.url
            response = self.client.post(
                set_password_url,
                {
                    "new_password1": "newpassword123!",
                    "new_password2": "newpassword123!",
                },
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Senha redefinida com sucesso")

        self.user.refresh_from_db()
        login_success = self.client.login(
            username="testuser", password="newpassword123!"
        )
        self.assertTrue(login_success)

    def test_login_page_has_recovery_link(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Esqueci minha senha")
        self.assertContains(response, reverse("password_recovery"))

    def test_must_change_password_flag_reset_after_recovery(self):
        if hasattr(self.user, "must_change_password"):
            self.user.must_change_password = True
            self.user.save()

            token = default_token_generator.make_token(self.user)
            uid = urlsafe_base64_encode(force_bytes(self.user.pk))

            confirm_url = reverse(
                "password_recovery_confirm", kwargs={"uidb64": uid, "token": token}
            )
            response = self.client.get(confirm_url)

            self.assertEqual(response.status_code, 302)
            set_password_url = response.url

            self.client.post(
                set_password_url,
                {
                    "new_password1": "newpassword123!",
                    "new_password2": "newpassword123!",
                },
                follow=True,
            )

            self.user.refresh_from_db()
            self.assertFalse(self.user.must_change_password)
