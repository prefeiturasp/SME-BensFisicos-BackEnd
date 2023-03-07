from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.contrib.auth import views as auth_views
from agendamento_suporte import urls as agenda_urls

admin.site.site_title = settings.ADMIN_SITE_TITLE
admin.site.site_header = settings.ADMIN_SITE_HEADER
admin.site.index_title = settings.ADMIN_INDEX_TITLE

urlpatterns = [
    path('', auth_views.LoginView.as_view(template_name='admin/login.html'), name='login'),  # new
    path('admin/', admin.site.urls),
    path('api/agenda/', include(agenda_urls.urlpatterns)),
]
