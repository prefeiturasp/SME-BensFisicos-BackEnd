from rest_framework.permissions import BasePermission


def _pode_acessar_modulo_inventario(user):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    return bool(
        getattr(user, "is_gestor_patrimonio", False)
        or getattr(user, "is_operador_inventario", False)
    )


class ConciliacaoUAPermission(BasePermission):
    """
    Regras de acesso para API de Conciliação (ConciliacaoUA):

    - Acesso ao módulo: gestor de patrimônio, operador de inventário ou superuser.
    - Listagem, detalhe, histórico, exportação, criação e finalização:
      qualquer perfil do módulo (espelha o admin, onde o operador possui as
      permissões add_conciliacaoua e change_conciliacaoua). O escopo de UA/UO
      é validado no queryset e no serializer.
    - Atualização/exclusão: bloqueadas (espelha o admin, que não permite
      editar/excluir conciliações).
    """

    def has_permission(self, request, view):
        if not _pode_acessar_modulo_inventario(request.user):
            return False

        action = getattr(view, "action", None)

        if action in ("list", "retrieve", "historico", "exportar",
                      "create", "finalizar"):
            return True

        if action in ("update", "partial_update", "destroy"):
            return False

        return True

    def has_object_permission(self, request, view, obj):
        action = getattr(view, "action", None)

        if action in ("update", "partial_update", "destroy"):
            return False

        return True


class ItemConciliacaoPermission(BasePermission):
    """
    Regras de acesso para API de Itens de Conciliação (ItemConciliacao):

    - Acesso ao módulo: gestor de patrimônio, operador de inventário ou superuser.
    - Listagem, detalhe e histórico: qualquer perfil do módulo.
    - Registrar/excluir ocorrência: qualquer perfil do módulo (escopo validado no queryset).
    - Criação/edição/exclusão direta de itens: bloqueadas (espelha o admin).
    """

    def has_permission(self, request, view):
        if not _pode_acessar_modulo_inventario(request.user):
            return False

        action = getattr(view, "action", None)

        if action in (
            "list",
            "retrieve",
            "historico",
            "registrar_ocorrencia",
            "excluir_ocorrencia",
            "situacoes_disponiveis",
        ):
            return True

        if action in ("create", "update", "partial_update", "destroy"):
            return False

        return True

    def has_object_permission(self, request, view, obj):
        action = getattr(view, "action", None)

        if action in ("create", "update", "partial_update", "destroy"):
            return False

        return True
