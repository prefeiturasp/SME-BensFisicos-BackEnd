from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied

from dados_comuns.escopo import filtrar_queryset_movimentacao_por_escopo


class BemPatrimonialPermission(BasePermission):
    """
    Espelha o admin:
    - Acesso ao módulo: gestor patrimônio OU operador inventário (ou superuser).
    - Change: bloqueia se excluido ou status final (igual has_change_permission).
    - Delete: só gestor, e bloqueia se excluido ou status final (igual has_delete_permission).
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

        status_finais = getattr(
            __import__("bem_patrimonial.constants", fromlist=["STATUS_FINAIS_BEM"]),
            "STATUS_FINAIS_BEM",
        )
        if getattr(obj, "status", None) in status_finais:
            if getattr(view, "action", None) in ("retrieve", "list", "historico"):
                return True
            return False

        if getattr(view, "action", None) == "destroy":
            return bool(
                getattr(user, "is_gestor_patrimonio", False)
                or getattr(user, "is_superuser", False)
            )

        return True


class MovimentacaoBemPatrimonialPermission(BasePermission):
    """
    Permissão para a API de movimentações:
    - acesso ao módulo: gestor, operador ou superuser;
    - leitura e ações de workflow respeitam a mesma regra de escopo do queryset.
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
        return self._pode_acessar_modulo(request.user)

    def has_object_permission(self, request, view, obj):
        from bem_patrimonial.models import MovimentacaoBemPatrimonial

        if not self._pode_acessar_modulo(request.user):
            return False

        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=obj.pk)
        return filtrar_queryset_movimentacao_por_escopo(request.user, queryset).exists()


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


class UnidadeOrcamentariaPermission(BasePermission):
    """
    Regras de acesso para API de Unidade Orçamentária:
    - Apenas superusuário acessa o módulo inteiro.
    """

    def _pode_acessar_modulo(self, user):
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "is_superuser", False)
        )

    def has_permission(self, request, view):
        return self._pode_acessar_modulo(request.user)

    def has_object_permission(self, request, view, obj):
        return self._pode_acessar_modulo(request.user)


class UsuarioPermission(BasePermission):
    """
    Regras de acesso para API de Usuários:

    - Apenas SUPERUSER e GESTOR podem acessar o módulo
    - Operador Inventário NÃO acessa gerenciamento de usuários
    """

    message = "Operador não acessa gerenciamento de usuários."

    def _pode_gerenciar(self, user):
        return bool(
            getattr(user, "is_superuser", False)
            or getattr(user, "is_gestor_patrimonio", False)
        )

    def has_permission(self, request, view):

        user = request.user

        if not self._pode_gerenciar(user):

            # bloquear operador explicitamente
            if getattr(user, "is_operador_inventario", False):
                raise PermissionDenied(self.message)

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
            return self._pode_gerenciar(user)

        return self._pode_gerenciar(user)

    def has_object_permission(self, request, view, obj):

        action = getattr(view, "action", None)

        # leitura
        if action == "retrieve":
            return True

        # escrita
        if action in ("update", "partial_update", "destroy", "restore"):
            return self._pode_gerenciar(request.user)

        return True
