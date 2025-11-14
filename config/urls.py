from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.contrib.auth import views as auth_views
from usuario.views import (
    LoginPasswordChangeView,
    LoginPasswordChangeDoneView,
    PasswordRecoveryRequestView,
    PasswordRecoveryDoneView,
    PasswordRecoveryConfirmView,
    PasswordRecoveryCompleteView,
)
from bem_patrimonial.views import download_documento_cimbpm
from django.shortcuts import redirect
from django.urls import reverse
from django.conf.urls.static import static
from django.conf import settings


# Módulo de Suporte desabilitado temporariamente
# from agendamento_suporte import urls as agenda_urls

admin.site.site_title = settings.ADMIN_SITE_TITLE
admin.site.site_header = settings.ADMIN_SITE_HEADER
admin.site.index_title = settings.ADMIN_INDEX_TITLE


def redirect_admin_password(request, user_id: int):
    next_url = reverse("admin:usuario_usuario_change", args=[user_id])
    url = f"{reverse('password_change')}?user_id={user_id}&next={next_url}"
    return redirect(url)


urlpatterns = [
    path(
        "", auth_views.LoginView.as_view(template_name="admin/login.html"), name="login"
    ),
    # Download protegido de documentos CIMBPM
    path(
        "documento-cimbpm/<int:pk>/download/",
        download_documento_cimbpm,
        name="download_documento_cimbpm",
    ),
    # Módulo de Suporte desabilitado temporariamente
    # path('api/agenda/', include(agenda_urls.urlpatterns)),
    # Recuperação de senha
    path(
        "admin/password-recovery/",
        PasswordRecoveryRequestView.as_view(),
        name="password_recovery",
    ),
    path(
        "admin/password-recovery/done/",
        PasswordRecoveryDoneView.as_view(),
        name="password_recovery_done",
    ),
    path(
        "admin/password-recovery/confirm/<uidb64>/<token>/",
        PasswordRecoveryConfirmView.as_view(),
        name="password_recovery_confirm",
    ),
    path(
        "admin/password-recovery/complete/",
        PasswordRecoveryCompleteView.as_view(),
        name="password_recovery_complete",
    ),
    # Troca de senha (usuário logado)
    path(
        "admin/usuario/usuario/<int:user_id>/password/",
        redirect_admin_password,
        name="admin_usuario_password_redirect",
    ),
    path(
        "admin/password-change/",
        LoginPasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "admin/password-change/done/",
        LoginPasswordChangeDoneView.as_view(),
        name="password_change_done",
    ),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
