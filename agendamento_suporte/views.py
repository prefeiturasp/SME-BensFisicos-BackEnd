import datetime
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework import viewsets
from agendamento_suporte.models import ConfigAgendaSuporte, AgendamentoSuporte
from agendamento_suporte.utils import gerar_horarios, dia_da_semana


class ConfigAgendaSuporteViewSet(viewsets.ViewSet):

    def retorna_horarios_disponiveis_por_dia(self, request):
        data = request.GET.get('data')

        agenda = ConfigAgendaSuporte.objects.first()
        dia = dia_da_semana(data)

        try:
            dia_semana = agenda.diasemana_set.get(dia_semana=dia)
        except Exception as e:
            dia_semana = None
            print(e)

        horarios = []

        if dia_semana:
            intervalos = dia_semana.intervalohoras_set.all()
            for item in intervalos:
                _horarios = gerar_horarios(item.hora_inicio, item.hora_fim)
                for _hr in _horarios:
                    horario_ja_esta_agendado = AgendamentoSuporte.objects.filter(data_agendada=data, hora_agendada=_hr).exists()
                    horario_valido = datetime.datetime.now().time() < datetime.datetime.strptime(_hr, '%H:%M').time()
                    if not horario_ja_esta_agendado and horario_valido:
                        horarios.append(_hr)

        horarios_ordenados = sorted(horarios, key=lambda x: datetime.datetime.strptime(x, '%H:%M'))
        return Response(horarios_ordenados)
