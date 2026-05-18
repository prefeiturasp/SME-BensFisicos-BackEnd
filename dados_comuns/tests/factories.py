# /code/dados_comuns/tests/factories.py

from dados_comuns.models import UnidadeOrcamentaria, UnidadeAdministrativa


def criar_uo(codigo="200", nome="UO Teste", sigla="UO", **kwargs):
    """
    Factory simples para UnidadeOrcamentaria alinhada ao model atual.
    """
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
    if uo is None:
        uo = criar_uo()

    data = {
        "codigo": codigo if codigo else "200",
        "sigla": sigla,
        "nome": nome if nome else "Unidade B",
        "status": status,
        "unidade_orcamentaria": uo,
        **kwargs,
    }
    return UnidadeAdministrativa.objects.create(**data)
