from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()

class PasswordChangeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="a123456")
        self.staff = User.objects.create_user(username="admin1", password="a123456", is_staff=True)

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
        resp = self.client.post(url, {
            "new_password1": "N0va@s3nhA!",
            "new_password2": "N0va@s3nhA!",
            "next": next_url,
        }, follow=False)

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
        resp = self.client.post(url, {
            "new_password1": "Sup3rS3nh@",
            "new_password2": "Sup3rS3nh@",
            "user_id": str(target.pk),
            "next": next_url,
        }, follow=False)

        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].endswith(next_url))

        target.refresh_from_db()
        self.assertFalse(target.must_change_password)
        self.assertIsNotNone(target.last_password_change)
        self.assertTrue(self.client.login(username="alice", password="Sup3rS3nh@"))