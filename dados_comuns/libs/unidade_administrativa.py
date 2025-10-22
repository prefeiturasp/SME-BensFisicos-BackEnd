from dados_comuns.models import UnidadeAdministrativa


def uas_do_usuario(user):
    if hasattr(user, "unidade_administrativa_id") and user.unidade_administrativa_id:
        return UnidadeAdministrativa.objects.filter(id=user.unidade_administrativa_id)
    return UnidadeAdministrativa.objects.none()