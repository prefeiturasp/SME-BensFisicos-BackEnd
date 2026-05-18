from django.db import models


PREFIXO_CODIGO_UO_SME = "01.16.10"
CODIGO_UA_PONTO_CENTRAL = "001"
NOME_UA_PONTO_CENTRAL = "Ponto Central"
SIGLA_UA_PONTO_CENTRAL = "PC"


def repr_value(value):
    if value is None:
        return ""
    if isinstance(value, models.Model):
        pk = getattr(value, "pk", None)
        try:
            return f"{pk} - {str(value)}"
        except Exception:
            return str(value)
    return str(value)


def dict_changes(original, updated, fields, only=None, ignore=None):
    """Retorna dict {field: (old_str, new_str)} para campos alterados."""
    ignore = set(ignore or [])
    if only is not None:
        fields = [f for f in fields if f in set(only)]

    changes = {}
    for f in fields:
        if f in ignore:
            continue
        old = getattr(original, f, None)
        new = getattr(updated, f, None)
        if repr_value(old) != repr_value(new):
            changes[f] = (repr_value(old), repr_value(new))
    return changes


def unidade_orcamentaria_eh_externa(unidade_orcamentaria):
    codigo = ((getattr(unidade_orcamentaria, "codigo", None) or "").strip())
    return bool(codigo) and not codigo.startswith(PREFIXO_CODIGO_UO_SME)


def garantir_ua_ponto_central_externa(unidade_orcamentaria):
    if not getattr(unidade_orcamentaria, "pk", None):
        return None, False

    if not unidade_orcamentaria_eh_externa(unidade_orcamentaria):
        return None, False

    from django.db.models import Q

    from dados_comuns.models import UnidadeAdministrativa

    codigo_esperado = (
        f"{unidade_orcamentaria.codigo.strip()}.{CODIGO_UA_PONTO_CENTRAL}"
    )
    ua = (
        UnidadeAdministrativa.objects.filter(
            unidade_orcamentaria=unidade_orcamentaria,
        )
        .filter(
            Q(codigo=codigo_esperado)
            | Q(codigo=CODIGO_UA_PONTO_CENTRAL)
            | Q(codigo__endswith=f".{CODIGO_UA_PONTO_CENTRAL}")
        )
        .order_by("id")
        .first()
    )

    if ua is None:
        ua = UnidadeAdministrativa.objects.create(
            unidade_orcamentaria=unidade_orcamentaria,
            codigo=codigo_esperado,
            sigla=SIGLA_UA_PONTO_CENTRAL,
            nome=NOME_UA_PONTO_CENTRAL,
            status=UnidadeAdministrativa.ATIVA,
        )
        return ua, True

    update_fields = []
    if ua.codigo != codigo_esperado:
        ua.codigo = codigo_esperado
        update_fields.append("codigo")
    if not ua.sigla:
        ua.sigla = SIGLA_UA_PONTO_CENTRAL
        update_fields.append("sigla")
    if not ua.nome:
        ua.nome = NOME_UA_PONTO_CENTRAL
        update_fields.append("nome")

    if update_fields:
        ua.save(update_fields=update_fields)

    return ua, False
