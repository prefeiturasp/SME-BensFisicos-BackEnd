from collections import defaultdict

from django.contrib import admin, messages
from django.db.models import Q
from django.template.response import TemplateResponse

from dados_comuns.libs.unidade_administrativa import uas_do_usuario


@admin.action(description="Verificar Movimentações Duplicadas")
def verificar_movimentacoes_duplicadas(modeladmin, request, queryset):
    """
    Lista movimentações potencialmente duplicadas, seguindo a regra:
    Para um mesmo bem, se ele saiu mais de uma vez da MESMA unidade de origem,
    essas movimentações formam um grupo que merece revisão.
    """

    user = request.user

    if not (
        getattr(user, "is_gestor_patrimonio", False)
        or getattr(user, "is_operador_inventario", False)
    ):
        messages.error(
            request,
            "Você não tem permissão para executar esta ação. "
            "Restrito a Gestor de Patrimônio ou Operador de Inventário.",
        )
        return None

    model = modeladmin.model

    changelist = modeladmin.get_changelist_instance(request)
    base_qs = changelist.get_queryset(request).select_related(
        "bem_patrimonial",
        "unidade_administrativa_origem",
        "unidade_administrativa_destino",
    )

    if getattr(user, "is_gestor_patrimonio", False):
        ua_user = getattr(user, "unidade_administrativa", None)
        if ua_user:
            base_qs = base_qs.filter(
                Q(unidade_administrativa_origem=ua_user)
                | Q(unidade_administrativa_destino=ua_user)
            )

    grupos = defaultdict(list)
    for mov in base_qs:
        chave = (mov.bem_patrimonial_id, mov.unidade_administrativa_origem_id)
        grupos[chave].append(mov)

    grupos_duplicados = []
    for (bem_id, origem_id), movimentos in grupos.items():
        if len(movimentos) <= 1:
            continue

        movimentos_ordenados = sorted(movimentos, key=lambda m: m.id or 0)

        grupos_duplicados.append(
            {
                "bem_id": bem_id,
                "bem": movimentos_ordenados[0].bem_patrimonial,
                "origem": movimentos_ordenados[0].unidade_administrativa_origem,
                "movimentos": movimentos_ordenados,
            }
        )

    grupos_duplicados.sort(
        key=lambda g: (
            str(g.get("bem_id") or ""),
            str(g.get("origem") or ""),
        )
    )

    context = modeladmin.admin_site.each_context(request)
    context.update(
        {
            "title": "(137771) Movimentações potencialmente duplicadas",
            "opts": model._meta,
            "grupos_duplicados": grupos_duplicados,
            "total_movimentacoes_analisadas": base_qs.count(),
            "total_grupos_duplicados": len(grupos_duplicados),
        }
    )

    return TemplateResponse(
        request,
        "admin/movimentacoes_duplicadas.html",
        context,
    )
