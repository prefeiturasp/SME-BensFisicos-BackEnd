from dados_comuns.models import UnidadeOrcamentaria, UnidadeAdministrativa


def criar_uo(codigo="200", nome="UO Teste", sigla="UO", **kwargs):
    data = {
        "codigo": codigo,
        "nome": nome,
        "sigla": sigla,
        **kwargs,
    }
    return UnidadeOrcamentaria.objects.create(**data)


def criar_ua(
    uo=None,
    codigo="200",
    sigla="UB",
    nome="Unidade B",
    status=UnidadeAdministrativa.ATIVA,
    **kwargs,
):
    # Aceita unidade_orcamentaria tanto via parâmetro posicional `uo`
    # quanto via kwargs (ex: criar_ua(unidade_orcamentaria=obj))
    if uo is None:
        uo = kwargs.pop("unidade_orcamentaria", None) or criar_uo()
    else:
        # Remove do kwargs caso venha duplicado
        kwargs.pop("unidade_orcamentaria", None)

    data = {
        "codigo": codigo if codigo else "200",
        "sigla": sigla,
        "nome": nome if nome else "Unidade B",
        "status": status,
        "unidade_orcamentaria": uo,
        **kwargs,
    }
    return UnidadeAdministrativa.objects.create(**data)
