from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.views import (
    LoginView,
    PasswordChangeView,
    PasswordResetView,
    PasswordResetConfirmView,
)
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.tokens import default_token_generator
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from urllib.parse import urlencode
from django.utils import timezone
from django.views.generic import TemplateView
from dados_comuns.models import HistoricoGeral, UnidadeAdministrativa
from dados_comuns.utils import dict_changes
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


class AdminLoginView(LoginView):
    template_name = "admin/login.html"

    def get_success_url(self):
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if next_url:
            return f"{reverse('selecionar_ua')}?{urlencode({'next': next_url})}"
        return reverse("selecionar_ua")


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


class SelecionarUAView(LoginRequiredMixin, TemplateView):
    template_name = "admin/selecionar_ua.html"
    login_url = "/admin/login/"
    VISAO_GERAL_VALUE = "__UO__"

    def _obter_uo_ativa(self, user):
        if user.unidade_orcamentaria_id:
            return user.unidade_orcamentaria
        if user.unidade_administrativa_id and user.unidade_administrativa:
            return user.unidade_administrativa.unidade_orcamentaria
        return None

    def get_uas_disponiveis(self):
        user = self.request.user
        if user.is_superuser:
            return UnidadeAdministrativa.objects.filter(
                status=UnidadeAdministrativa.ATIVA
            ).select_related("unidade_orcamentaria")
        if user.is_gestor_patrimonio:
            uo_id = user.unidade_orcamentaria_id
            if uo_id:
                return UnidadeAdministrativa.objects.filter(
                    unidade_orcamentaria_id=uo_id,
                    status=UnidadeAdministrativa.ATIVA,
                ).select_related("unidade_orcamentaria")
        return user.unidades_administrativas.filter(
            status=UnidadeAdministrativa.ATIVA
        ).select_related("unidade_orcamentaria")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        uo_ativa = self._obter_uo_ativa(user)
        permite_visao_geral = bool(user.is_superuser or user.is_gestor_patrimonio)

        ctx["uas_disponiveis"] = self.get_uas_disponiveis()
        ctx["ua_ativa_id"] = user.unidade_administrativa_id
        ctx["uo_ativa"] = uo_ativa
        ctx["permite_visao_geral"] = permite_visao_geral and bool(uo_ativa)
        ctx["visao_geral_value"] = self.VISAO_GERAL_VALUE
        ctx["visao_geral_selected"] = (
            permite_visao_geral and not user.unidade_administrativa_id
        )
        ctx["next"] = self.request.GET.get("next", reverse("admin:index"))
        ctx["error"] = None
        return ctx

    def _save_user_ua_uo_historico(self, user, update_fields):
        from usuario.models import Usuario

        original = Usuario.objects.get(pk=user.pk)
        with transaction.atomic():
            if update_fields:
                user.save(update_fields=update_fields)
                changes = dict_changes(
                    original,
                    user,
                    fields=["unidade_administrativa", "unidade_orcamentaria"],
                )
                if changes:
                    ct = ContentType.objects.get_for_model(Usuario)
                    HistoricoGeral.objects.bulk_create(
                        [
                            HistoricoGeral(
                                content_type=ct,
                                object_id=str(user.pk),
                                campo=field,
                                valor_antigo=old,
                                valor_novo=new,
                                alterado_por=user,
                            )
                            for field, (old, new) in changes.items()
                        ]
                    )

    def _post_visao_geral(self, request, next_url):
        user = request.user
        if not (user.is_superuser or user.is_gestor_patrimonio):
            ctx = self.get_context_data()
            ctx["error"] = (
                "A visão geral da UO é permitida apenas para gestor e superusuário."
            )
            return self.render_to_response(ctx)
        uo_ativa = self._obter_uo_ativa(user)
        if not uo_ativa:
            ctx = self.get_context_data()
            ctx["error"] = (
                "Não foi possível identificar a Unidade Orçamentária para visão geral."
            )
            return self.render_to_response(ctx)
        if not uo_ativa.ativa:
            ctx = self.get_context_data()
            ctx["error"] = "A Unidade Orçamentária vinculada está inativa."
            return self.render_to_response(ctx)
        update_fields = []
        if user.unidade_administrativa_id is not None:
            user.unidade_administrativa = None
            update_fields.append("unidade_administrativa")
        if user.unidade_orcamentaria_id != uo_ativa.id:
            user.unidade_orcamentaria = uo_ativa
            update_fields.append("unidade_orcamentaria")
        self._save_user_ua_uo_historico(user, update_fields)
        return redirect(next_url)

    def _post_ua_especifica(self, request, ua_id, next_url):
        user = request.user
        uas_disponiveis = self.get_uas_disponiveis()
        if not uas_disponiveis.filter(id=ua_id).exists():
            ctx = self.get_context_data()
            ctx["error"] = (
                "Você não tem permissão para acessar essa Unidade Administrativa."
            )
            return self.render_to_response(ctx)
        ua = UnidadeAdministrativa.objects.get(id=ua_id)
        update_fields = []
        if user.unidade_administrativa_id != ua.id:
            user.unidade_administrativa = ua
            update_fields.append("unidade_administrativa")
        if (
            ua.unidade_orcamentaria_id
            and user.unidade_orcamentaria_id != ua.unidade_orcamentaria_id
        ):
            user.unidade_orcamentaria = ua.unidade_orcamentaria
            update_fields.append("unidade_orcamentaria")
        self._save_user_ua_uo_historico(user, update_fields)
        return redirect(next_url)

    def post(self, request, *args, **kwargs):
        ua_id = request.POST.get("unidade_administrativa")
        next_url = request.POST.get("next", reverse("admin:index"))

        if ua_id == self.VISAO_GERAL_VALUE:
            return self._post_visao_geral(request, next_url)

        if not ua_id:
            ctx = self.get_context_data()
            ctx["error"] = "Selecione uma Unidade Administrativa."
            return self.render_to_response(ctx)

        try:
            ua_id = int(ua_id)
        except (ValueError, TypeError):
            ctx = self.get_context_data()
            ctx["error"] = "Unidade Administrativa inválida."
            return self.render_to_response(ctx)

        return self._post_ua_especifica(request, ua_id, next_url)
