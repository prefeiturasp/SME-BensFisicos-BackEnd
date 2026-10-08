from collections import defaultdict

from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType

from dados_comuns.models import HistoricoGeral


def _eh_criacao_usuario(registro):
    return registro.campo == "" and registro.justificativa == "Usuário criado"


def _operacao_registro(registro):
    if _eh_criacao_usuario(registro) or (
        registro.campo == "acao" and registro.valor_novo == "criado"
    ):
        return "criacao"
    return "alteracao"


def _acao_registro(registro):
    criacao_usuario = _eh_criacao_usuario(registro)
    return {
        "campo": "acao" if criacao_usuario else registro.campo,
        "valor_antigo": registro.valor_antigo,
        "valor_novo": "criado" if criacao_usuario else registro.valor_novo,
        "justificativa": registro.justificativa,
    }


def _grupo_registros(data, usuario_id, itens):
    usuario = itens[0].alterado_por
    return {
        "alterado_em": data,
        "alterado_por": usuario_id,
        "alterado_por_nome": usuario.nome if usuario else None,
        "alterado_por_rf": usuario.rf if usuario else None,
        "acoes": [_acao_registro(item) for item in itens],
    }


def _consultar_registros(content_type, objeto_id):
    registros = (
        HistoricoGeral.objects.filter(content_type=content_type, object_id=str(objeto_id))
        .select_related("alterado_por")
        .order_by("-alterado_em", "-id")
    )
    agrupados = defaultdict(list)
    for registro in registros:
        chave = (
            registro.alterado_em.replace(microsecond=0),
            registro.alterado_por_id,
            _operacao_registro(registro),
        )
        agrupados[chave].append(registro)

    return [
        _grupo_registros(data, usuario_id, itens)
        for (data, usuario_id, _), itens in agrupados.items()
    ]


def _grupo_log(log):
    usuario = log.user
    operacao = "criado" if log.is_addition() else "alterado"
    if log.is_deletion():
        operacao = "excluido"
    return {
        "alterado_em": log.action_time,
        "alterado_por": usuario.pk if usuario else None,
        "alterado_por_nome": usuario.nome if usuario else None,
        "alterado_por_rf": usuario.rf if usuario else None,
        "acoes": [
            {
                "campo": "acao",
                "valor_antigo": "",
                "valor_novo": operacao,
                "justificativa": log.get_change_message() or None,
            }
        ],
    }


def _consultar_logs(content_type, objeto_id):
    logs = (
        LogEntry.objects.filter(content_type=content_type, object_id=str(objeto_id))
        .select_related("user")
        .order_by("-action_time", "-id")
    )
    return [_grupo_log(log) for log in logs]


def consultar_historico(modelo, objeto_id):
    content_type = ContentType.objects.get_for_model(modelo)
    resultado = _consultar_registros(content_type, objeto_id)
    resultado.extend(_consultar_logs(content_type, objeto_id))
    return sorted(resultado, key=lambda item: item["alterado_em"], reverse=True)
