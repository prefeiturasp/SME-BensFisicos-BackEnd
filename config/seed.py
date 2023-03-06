import django
import os
import sys
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

from agendamento_suporte.constants import MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY
from agendamento_suporte.models import ConfigAgendaSuporte, DiaSemana


def db_seed():
    weekdays = [MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY]
    agenda, _ = ConfigAgendaSuporte.objects.get_or_create(nome="Agenda setor")
    for item in weekdays:
        DiaSemana.objects.get_or_create(
            agenda=agenda,
            dia_semana=item
        )


if __name__ == "__main__":
    print("Iniciado o script...")
    db_seed()
    print("Pronto! :)")