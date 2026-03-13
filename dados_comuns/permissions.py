from rest_framework.permissions import BasePermission


class BemPatrimonialPermission(BasePermission):
    """
    Espelha o admin:
    - Acesso ao módulo: gestor patrimônio OU operador inventário (ou superuser).
    - Change: bloqueia se excluido ou BAIXA_FISICA (igual has_change_permission).
    - Delete: só gestor, e bloqueia se excluido ou BAIXA_FISICA (igual has_delete_permission).
    """

    def _pode_acessar_modulo(self, user):
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return bool(
            getattr(user, "is_gestor_patrimonio", False)
            or getattr(user, "is_operador_inventario", False)
        )

    def has_permission(self, request, view):
        if not self._pode_acessar_modulo(request.user):
            return False

        if getattr(view, "action", None) == "create":
            return True

        if getattr(view, "action", None) in ("list", "retrieve"):
            return True

        if getattr(view, "action", None) in ("update", "partial_update"):
            return True

        if getattr(view, "action", None) == "destroy":
            return bool(
                getattr(request.user, "is_gestor_patrimonio", False)
                or getattr(request.user, "is_superuser", False)
            )

        return True

    def has_object_permission(self, request, view, obj):
        user = request.user

        if getattr(obj, "excluido", False):
            return False

        if getattr(obj, "status", None) == getattr(
            __import__("bem_patrimonial.constants", fromlist=["BAIXA_FISICA"]),
            "BAIXA_FISICA",
        ):
            if getattr(view, "action", None) in ("retrieve", "list", "historico"):
                return True
            return False

        if getattr(view, "action", None) == "destroy":
            return bool(
                getattr(user, "is_gestor_patrimonio", False)
                or getattr(user, "is_superuser", False)
            )

        return True


class UnidadeAdministrativaPermission(BasePermission):
    """
    Regras de acesso para API de Unidade Administrativa:
    - Listagem/detalhe/historico: superuser, gestor e operador.
    - Criacao/edicao/exclusao/exportacao: apenas superuser e gestor.
    """

    def _pode_acessar_modulo(self, user):
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return bool(
            getattr(user, "is_gestor_patrimonio", False)
            or getattr(user, "is_operador_inventario", False)
        )

    def _pode_gerenciar(self, user):
        return bool(
            getattr(user, "is_superuser", False)
            or getattr(user, "is_gestor_patrimonio", False)
        )

    def has_permission(self, request, view):
        if not self._pode_acessar_modulo(request.user):
            return False

        action = getattr(view, "action", None)

        if action in ("list", "retrieve", "historico"):
            return True

        if action in ("create", "update", "partial_update", "destroy", "exportar"):
            return self._pode_gerenciar(request.user)

        return self._pode_gerenciar(request.user)

    def has_object_permission(self, request, view, obj):
        action = getattr(view, "action", None)

        if action in ("retrieve", "historico"):
            return True

        if action in ("update", "partial_update", "destroy"):
            return self._pode_gerenciar(request.user)

        return True


class UsuarioPermission(BasePermission):
    """
        Regras de acesso para API de Usuários:

        - Listagem/detalhe: superuser, gestor e operador
        - Criacao/edicao/desativacao/reativacao: apenas superuser e gestor
    """

    def _pode_acessar_modulo(self, user):
        if not user or not user.is_authenticated:
            return False

        if getattr(user, "is_superuser", False):
            return True

        return bool(
            getattr(user, "is_gestor_patrimonio", False)
            or getattr(user, "is_operador_inventario", False)
        )

    def _pode_gerenciar(self, user):
        return bool(
            getattr(user, "is_superuser", False)
            or getattr(user, "is_gestor_patrimonio", False)
        )

    def has_permission(self, request, view):
        if not self._pode_acessar_modulo(request.user):
            return False

        action = getattr(view, "action", None)

        # leitura
        if action in ("list", "retrieve"):
            return True

        # escrita
        if action in (
            "create",
            "update",
            "partial_update",
            "destroy",
            "restore",
        ):
            return self._pode_gerenciar(request.user)

        return self._pode_gerenciar(request.user)

    def has_object_permission(self, request, view, obj):
        action = getattr(view, "action", None)

        # leitura sempre permitida se passou no has_permission
        if action in ("retrieve",):
            return True

        # edição/desativação
        if action in ("update", "partial_update", "destroy", "restore"):
            return self._pode_gerenciar(request.user)

        return True
