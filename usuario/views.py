from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.views import (
    PasswordChangeView,
    PasswordResetView,
    PasswordResetConfirmView,
)
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class LoginPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    template_name = "admin/password_change.html"
    success_url = reverse_lazy("password_change_done")
    form_class = SetPasswordForm

    def dispatch(self, request, *args, **kwargs):
        user_id = request.GET.get("user_id") or request.POST.get("user_id")
        if user_id and request.user.is_staff:
            self.user_to_change = get_object_or_404(User, pk=user_id)
        else:
            self.user_to_change = request.user
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.user_to_change
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["user_id"] = (
            self.request.GET.get("user_id")
            or self.request.POST.get("user_id")
            or (self.user_to_change.pk if self.user_to_change else None)
        )
        ctx["next"] = self.request.GET.get("next") or self.request.POST.get("next")
        return ctx

    def form_valid(self, form):
        resp = super().form_valid(form)
        updates = []
        if (
            hasattr(self.user_to_change, "must_change_password")
            and self.user_to_change.must_change_password
        ):
            self.user_to_change.must_change_password = False
            updates.append("must_change_password")
        if hasattr(self.user_to_change, "last_password_change"):
            self.user_to_change.last_password_change = timezone.now()
            updates.append("last_password_change")
        if updates:
            self.user_to_change.save(update_fields=updates)
        return resp

    def get_success_url(self):
        nxt = self.request.POST.get("next") or self.request.GET.get("next")
        return nxt or super().get_success_url()


class LoginPasswordChangeDoneView(LoginRequiredMixin, TemplateView):
    template_name = "admin/password_change_done.html"


class PasswordRecoveryRequestView(PasswordResetView):

    template_name = "admin/password_recovery_request.html"
    email_template_name = "admin/password_recovery_email.html"
    success_url = reverse_lazy("password_recovery_done")
    token_generator = default_token_generator
    from_email = None
    html_email_template_name = "admin/password_recovery_email.html"
    subject = "[Bens Físicos] Recuperação de senha solicitada"

    def get_users(self, email):
        active_users = User.objects.filter(email__iexact=email, is_active=True)
        return (u for u in active_users if u.has_usable_password())

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        logger.info(f"Solicitação de recuperação de senha para {email}")
        return super().form_valid(form)


class PasswordRecoveryDoneView(TemplateView):
    
    template_name = "admin/password_recovery_done.html"


class PasswordRecoveryConfirmView(PasswordResetConfirmView):

    template_name = "admin/password_recovery_confirm.html"
    success_url = reverse_lazy("password_recovery_complete")
    token_generator = default_token_generator

    def form_valid(self, form):
        user = form.save()

        updates = []
        if hasattr(user, "must_change_password"):
            user.must_change_password = False
            updates.append("must_change_password")
        if hasattr(user, "last_password_change"):
            user.last_password_change = timezone.now()
            updates.append("last_password_change")

        if updates:
            user.save(update_fields=updates)

        logger.info(f"Senha recuperada com sucesso para usuário {user.username}")
        return super().form_valid(form)


class PasswordRecoveryCompleteView(TemplateView):

    template_name = "admin/password_recovery_complete.html"
