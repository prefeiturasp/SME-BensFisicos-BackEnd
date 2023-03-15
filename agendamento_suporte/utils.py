import datetime
from agendamento_suporte.constants import MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY
from agendamento_suporte.models import ConfigAgendaSuporte, DiaSemana


def setup_dias_semana_agenda_unica():
    weekdays = [MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY]
    agenda, _ = ConfigAgendaSuporte.objects.get_or_create(id=1, defaults={"nome": "Agenda setor"})
    for item in weekdays:
        dia, _ = DiaSemana.objects.get_or_create(
            agenda=agenda,
            dia_semana=item
        )
        print('{} => ok'.format(dia.get_day_week_display()))


def gerar_horarios(horario_inicio, horario_fim):
    # Converter as strings de entrada para objetos datetime.time
    inicio = horario_inicio
    fim = horario_fim

    # Definir o período de incremento (30 minutos)
    incremento = datetime.timedelta(minutes=30)

    # Inicializar o array de horários
    horarios = []

    # Definir o horário inicial
    horario_atual = datetime.datetime.combine(datetime.date.today(), inicio)

    # Percorrer todos os horários no intervalo especificado
    while horario_atual.time() <= fim:
        # Adicionar o horário atual ao array de horários
        horarios.append(horario_atual.time().strftime('%H:%M'))

        # Incrementar o horário atual
        horario_atual += incremento

    return horarios


def dia_da_semana(data):
    # Converter a string de entrada para um objeto datetime.date
    data_obj = datetime.datetime.strptime(data, '%Y-%m-%d').date()

    # Definir os nomes dos dias da semana
    dias_da_semana = [MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY]

    # Obter o índice do dia da semana (0 = segunda-feira, 1 = terça-feira, etc.)
    dia_da_semana_idx = data_obj.weekday()

    # Retornar o nome do dia da semana correspondente
    # return dias_da_semana[dia_da_semana_idx]

    return dias_da_semana[dia_da_semana_idx]
