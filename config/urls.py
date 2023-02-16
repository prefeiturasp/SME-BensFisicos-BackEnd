from django.contrib import admin
from django.urls import path
from django.conf import settings

admin.site.site_title = settings.ADMIN_SITE_TITLE
admin.site.site_header = settings.ADMIN_SITE_HEADER
admin.site.index_title = settings.ADMIN_INDEX_TITLE

urlpatterns = [
    path('', admin.site.urls),
]
