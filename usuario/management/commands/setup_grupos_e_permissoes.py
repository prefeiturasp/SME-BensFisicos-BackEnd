from django.core.management.base import BaseCommand
from usuario.utils import setup_grupos_e_permissoes


class Command(BaseCommand):
    help = '''Cria grupos e atribui permissoes pertinentes a cada grupo'''

    def handle(self, *args, **options):
        setup_grupos_e_permissoes()
