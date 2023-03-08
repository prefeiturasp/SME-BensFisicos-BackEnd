from django.urls import path
from .views import ConfigAgendaSuporteViewSet

app_name = "agenda"

urlpatterns = [
    path('horarios_disponiveis/', ConfigAgendaSuporteViewSet.as_view({'get': 'retorna_horarios_disponiveis_por_dia'})),
]
