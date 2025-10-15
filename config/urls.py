from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.contrib.auth import views as auth_views
from usuario.views import LoginPasswordChangeView, LoginPasswordChangeDoneView
from django.shortcuts import redirect
from django.urls import reverse

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
    ),  # new
    # Módulo de Suporte desabilitado temporariamente
    # path('api/agenda/', include(agenda_urls.urlpatterns)),
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
