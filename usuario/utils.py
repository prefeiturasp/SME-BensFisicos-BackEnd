import operator
from functools import reduce
from django.contrib.auth.models import Group, Permission
from django.db.models import Q
from usuario.constants import GRUPO_OPERADOR_INVENTARIO, GRUPO_GESTOR_PATRIMONIO


def setup_grupos_e_permissoes():
    '''Criar grupos e define permissões.'''

    # setup gestor
    gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
    gestor_settings = {
        'bempatrimonial': ['add', 'change', 'delete', 'view'],
        '_agendamentosuporte': ['add', 'change', 'delete', 'view'],
        '_usuario': ['add', 'change', 'view'],
        '_configagendasuporte': ['view', 'change'],
        '_diasemana': ['view'],
        '_intervalohoras': ['add', 'change', 'delete', 'view'],
        '_unidadeadministrativa': ['add', 'change', 'delete', 'view']
    }
    for key in gestor_settings:
        verbs = gestor_settings[key]
        permission = Permission.objects.filter(Q(codename__contains=key) & reduce(operator.or_, (Q(codename__contains=x) for x in verbs)))
        gestor.permissions.add(*permission)

    # setup operador
    operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
    operador_settings = {
        '_bempatrimonial': ['add', 'change', 'delete', 'view'],
        '_historicostatusbempatrimonial': ['view'],
        '_agendamentosuporte': ['add', 'change', 'delete', 'view'],
    }
    for key in operador_settings:
        verbs = operador_settings[key]
        permission = Permission.objects.filter(Q(codename__contains=key) & reduce(operator.or_, (Q(codename__contains=x) for x in verbs)))
        operador.permissions.add(*permission)
