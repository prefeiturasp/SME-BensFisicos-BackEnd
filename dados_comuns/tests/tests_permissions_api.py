from types import SimpleNamespace

from django.test import SimpleTestCase

from bem_patrimonial import constants as bem_constants
from dados_comuns.permissions import (
    BemPatrimonialPermission,
    UnidadeAdministrativaPermission,
)


class PermissionsAPITestCase(SimpleTestCase):
    def _request(self, user):
        return SimpleNamespace(user=user)

    def _view(self, action):
        return SimpleNamespace(action=action)

    def _user(
        self,
        *,
        authenticated=True,
        superuser=False,
        gestor=False,
        operador=False,
    ):
        return SimpleNamespace(
            is_authenticated=authenticated,
            is_superuser=superuser,
            is_gestor_patrimonio=gestor,
            is_operador_inventario=operador,
        )

    def test_bem_has_permission_cobre_ramos_principais(self):
        perm = BemPatrimonialPermission()

        user_sem_auth = self._user(authenticated=False)
        self.assertFalse(perm.has_permission(self._request(user_sem_auth), self._view("list")))

        user_super = self._user(superuser=True)
        for action in ("create", "list", "retrieve", "update", "partial_update", "foo"):
            with self.subTest(action=action):
                self.assertTrue(perm.has_permission(self._request(user_super), self._view(action)))

        user_operador = self._user(operador=True)
        self.assertFalse(
            perm.has_permission(self._request(user_operador), self._view("destroy"))
        )

        user_gestor = self._user(gestor=True)
        self.assertTrue(
            perm.has_permission(self._request(user_gestor), self._view("destroy"))
        )

    def test_bem_has_object_permission_cobre_ramos(self):
        perm = BemPatrimonialPermission()
        user_operador = self._user(operador=True)
        user_gestor = self._user(gestor=True)

        excluido = SimpleNamespace(excluido=True, status="qualquer")
        self.assertFalse(
            perm.has_object_permission(self._request(user_gestor), self._view("retrieve"), excluido)
        )

        baixa = SimpleNamespace(excluido=False, status=bem_constants.BAIXA_FISICA)
        self.assertTrue(
            perm.has_object_permission(self._request(user_gestor), self._view("retrieve"), baixa)
        )
        self.assertTrue(
            perm.has_object_permission(self._request(user_gestor), self._view("historico"), baixa)
        )
        self.assertFalse(
            perm.has_object_permission(self._request(user_gestor), self._view("update"), baixa)
        )

        normal = SimpleNamespace(excluido=False, status="ativo")
        self.assertFalse(
            perm.has_object_permission(self._request(user_operador), self._view("destroy"), normal)
        )
        self.assertTrue(
            perm.has_object_permission(self._request(user_gestor), self._view("destroy"), normal)
        )
        self.assertTrue(
            perm.has_object_permission(self._request(user_operador), self._view("update"), normal)
        )

    def test_ua_has_permission_cobre_ramos_principais(self):
        perm = UnidadeAdministrativaPermission()

        self.assertFalse(
            perm.has_permission(self._request(self._user(authenticated=False)), self._view("list"))
        )

        superuser = self._user(superuser=True)
        for action in (
            "list",
            "retrieve",
            "historico",
            "create",
            "update",
            "partial_update",
            "destroy",
            "exportar",
            "acao_desconhecida",
        ):
            with self.subTest(action=action):
                self.assertTrue(perm.has_permission(self._request(superuser), self._view(action)))

        operador = self._user(operador=True)
        self.assertTrue(perm.has_permission(self._request(operador), self._view("list")))
        self.assertTrue(perm.has_permission(self._request(operador), self._view("historico")))
        self.assertFalse(perm.has_permission(self._request(operador), self._view("create")))
        self.assertFalse(perm.has_permission(self._request(operador), self._view("acao_desconhecida")))

    def test_ua_has_object_permission_cobre_ramos(self):
        perm = UnidadeAdministrativaPermission()
        operador = self._user(operador=True)
        gestor = self._user(gestor=True)
        obj = SimpleNamespace()

        self.assertTrue(
            perm.has_object_permission(self._request(operador), self._view("retrieve"), obj)
        )
        self.assertTrue(
            perm.has_object_permission(self._request(operador), self._view("historico"), obj)
        )

        self.assertFalse(
            perm.has_object_permission(self._request(operador), self._view("destroy"), obj)
        )
        self.assertTrue(
            perm.has_object_permission(self._request(gestor), self._view("destroy"), obj)
        )

        self.assertFalse(
            perm.has_object_permission(self._request(operador), self._view("update"), obj)
        )
        self.assertTrue(
            perm.has_object_permission(self._request(gestor), self._view("partial_update"), obj)
        )

        self.assertTrue(
            perm.has_object_permission(self._request(operador), self._view("acao_desconhecida"), obj)
        )
