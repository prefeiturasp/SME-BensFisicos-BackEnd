from django.core.management.base import BaseCommand
from agendamento_suporte.utils import setup_dias_semana_agenda_unica


class Command(BaseCommand):
    help = '''Setup dias da semana para agenda'''

    def handle(self, *args, **options):
        setup_dias_semana_agenda_unica()
