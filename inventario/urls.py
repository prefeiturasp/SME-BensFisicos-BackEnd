from django.urls import path
from inventario.views import download_conciliacao_pdf

urlpatterns = [
    path(
        "inventario/conciliacao/<int:pk>/exportar/",
        download_conciliacao_pdf,
        name="download_conciliacao_pdf",
    ),
]
