from collections import defaultdict

from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType

from dados_comuns.models import HistoricoGeral


def consultar_historico(modelo, objeto_id):
    content_type = ContentType.objects.get_for_model(modelo)
    registros = (
        HistoricoGeral.objects.filter(content_type=content_type, object_id=str(objeto_id))
        .select_related("alterado_por")
        .order_by("-alterado_em", "-id")
    )
    agrupados = defaultdict(list)
    for registro in registros:
        criacao_usuario = registro.campo == "" and registro.justificativa == "Usuário criado"
        operacao = "criacao" if criacao_usuario or (registro.campo == "acao" and registro.valor_novo == "criado") else "alteracao"
        chave = (registro.alterado_em.replace(microsecond=0), registro.alterado_por_id, operacao)
        agrupados[chave].append(registro)

    resultado = []
    for (data, usuario_id, _), itens in agrupados.items():
        usuario = itens[0].alterado_por
        acoes = []
        for item in itens:
            criacao_usuario = item.campo == "" and item.justificativa == "Usuário criado"
            acoes.append(
                {
                    "campo": "acao" if criacao_usuario else item.campo,
                    "valor_antigo": item.valor_antigo,
                    "valor_novo": "criado" if criacao_usuario else item.valor_novo,
                    "justificativa": item.justificativa,
                }
            )
        resultado.append(
            {
                "alterado_em": data,
                "alterado_por": usuario_id,
                "alterado_por_nome": usuario.nome if usuario else None,
                "alterado_por_rf": usuario.rf if usuario else None,
                "acoes": acoes,
            }
        )

    logs = (
        LogEntry.objects.filter(content_type=content_type, object_id=str(objeto_id))
        .select_related("user")
        .order_by("-action_time", "-id")
    )
    for log in logs:
        usuario = log.user
        operacao = "criado" if log.is_addition() else "alterado"
        if log.is_deletion():
            operacao = "excluido"
        resultado.append(
            {
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
        )

    return sorted(resultado, key=lambda item: item["alterado_em"], reverse=True)
