from django.contrib.auth.models import Group, Permission
from usuario.constants import GRUPO_OPERADOR_INVENTARIO, GRUPO_GESTOR_PATRIMONIO


def atribuir_permissao(grupo, settings):
    verb_options = ["add", "change", "delete", "view"]

    for key in settings:
        verbs_by_key = settings[key]

        for permission in Permission.objects.all():
            for verb in verb_options:
                if (verb + key == permission.codename) and verb in verbs_by_key:
                    grupo.permissions.add(permission)
                    print(
                        "Permissão adicionada ao grupo {} => {}".format(
                            grupo, permission.codename
                        )
                    )


def setup_grupos_e_permissoes():
    """Cria grupos e atribui permissões."""

    # setup gestor
    gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
    gestor_settings = {
        "_bempatrimonial": ["add", "change", "delete", "view"],
        "_movimentacaobempatrimonial": ["add", "change", "delete", "view"],
        "_unidadeadministrativabempatrimonial": ["view"],
        "_statusbempatrimonial": ["add", "change", "delete", "view"],
        "_usuario": ["add", "change", "view"],
        "_unidadeadministrativa": ["add", "change", "delete", "view"],
        # Módulo de Suporte desabilitado temporariamente
        # '_agendamentosuporte': ['add', 'change', 'delete', 'view'],
        # '_configagendasuporte': ['view', 'change'],
        # '_diasemana': ['view'],
        # '_intervalohoras': ['add', 'change', 'delete', 'view'],
    }
    atribuir_permissao(gestor, gestor_settings)

    # setup operador
    operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
    operador_settings = {
        "_bempatrimonial": ["add", "change", "delete", "view"],
        "_unidadeadministrativabempatrimonial": ["view"],
        "_movimentacaobempatrimonial": ["add", "change", "view"],
        "_statusbempatrimonial": ["view"],
        # Módulo de Suporte desabilitado temporariamente
        # '_agendamentosuporte': ['add', 'change', 'delete', 'view'],
    }
    atribuir_permissao(operador, operador_settings)
