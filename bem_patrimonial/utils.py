from copy import copy


def duplicar_e_retornar_nova_instancia(bem_patrimonial):
    historico_status = bem_patrimonial.historicostatusbempatrimonial_set.all()

    new_instance = copy(bem_patrimonial)
    new_instance.pk = None
    new_instance.save()

    for _status in historico_status:
        _status.pk = None
        _status.bem_patrimonial = new_instance
        _status.save()

    return new_instance
