from django.contrib.auth import get_user_model
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth.views import PasswordChangeView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import TemplateView

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
