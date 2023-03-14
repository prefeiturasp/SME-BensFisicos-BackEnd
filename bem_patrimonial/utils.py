from copy import copy


def duplicar_e_retornar_nova_instancia(instancia):
    nova_instancia = copy(instancia)
    nova_instancia.pk = None
    nova_instancia.save()

    return nova_instancia
