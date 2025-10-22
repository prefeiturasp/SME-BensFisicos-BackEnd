from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.contrib.auth import get_user_model

User = get_user_model()


@receiver(user_logged_in, dispatch_uid="mark_first_admin_login", weak=False)
def mark_first_admin_login(sender, user, request, **kwargs):
    # lê do banco o valor prévio
    prev = User.objects.filter(pk=user.pk).values_list("last_login", flat=True).first()
    if prev is None:
        request.session["force_pw_change_first_admin"] = True
