from types import SimpleNamespace

from django.test import SimpleTestCase

from inventario.permissions import (
    ConciliacaoUAPermission,
    ItemConciliacaoPermission,
)


class PermissionsInventarioAPITestCase(SimpleTestCase):
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

    def test_conciliacao_has_permission_cobre_ramos_principais(self):
        perm = ConciliacaoUAPermission()

        user_sem_auth = self._user(authenticated=False)
        self.assertFalse(
            perm.has_permission(self._request(user_sem_auth), self._view("list"))
        )

        user_super = self._user(superuser=True)
        for action in ("list", "retrieve", "create", "historico", "exportar", "finalizar"):
            with self.subTest(action=action):
                self.assertTrue(
                    perm.has_permission(self._request(user_super), self._view(action))
                )

        user_gestor = self._user(gestor=True)
        for action in ("list", "retrieve", "create", "historico", "exportar", "finalizar"):
            with self.subTest(action=action):
                self.assertTrue(
                    perm.has_permission(self._request(user_gestor), self._view(action))
                )

        user_operador = self._user(operador=True)
        for action in ("list", "retrieve", "create", "historico",
                       "exportar", "finalizar"):
            with self.subTest(action=action):
                self.assertTrue(
                    perm.has_permission(self._request(user_operador), self._view(action))
                )

    def test_conciliacao_bloqueia_update_e_delete(self):
        perm = ConciliacaoUAPermission()
        user_gestor = self._user(gestor=True)

        for action in ("update", "partial_update", "destroy"):
            with self.subTest(action=action):
                self.assertFalse(
                    perm.has_permission(self._request(user_gestor), self._view(action))
                )

    def test_conciliacao_has_object_permission_bloqueia_update_e_delete(self):
        perm = ConciliacaoUAPermission()
        user_gestor = self._user(gestor=True)
        user_operador = self._user(operador=True)
        obj = SimpleNamespace()

        for action in ("update", "partial_update", "destroy"):
            with self.subTest(action=action):
                self.assertFalse(
                    perm.has_object_permission(
                        self._request(user_gestor), self._view(action), obj
                    )
                )

        for action in ("retrieve", "historico", "exportar", "finalizar"):
            with self.subTest(action=action):
                self.assertTrue(
                    perm.has_object_permission(
                        self._request(user_gestor), self._view(action), obj
                    )
                )

        for action in ("retrieve", "historico", "exportar", "finalizar"):
            with self.subTest(action=action):
                self.assertTrue(
                    perm.has_object_permission(
                        self._request(user_operador), self._view(action), obj
                    )
                )

    def test_item_has_permission_cobre_ramos_principais(self):
        perm = ItemConciliacaoPermission()

        user_sem_auth = self._user(authenticated=False)
        self.assertFalse(
            perm.has_permission(self._request(user_sem_auth), self._view("list"))
        )

        user_super = self._user(superuser=True)
        for action in (
            "list",
            "retrieve",
            "historico",
            "registrar_ocorrencia",
            "excluir_ocorrencia",
            "situacoes_disponiveis",
        ):
            with self.subTest(action=action):
                self.assertTrue(
                    perm.has_permission(self._request(user_super), self._view(action))
                )

        user_gestor = self._user(gestor=True)
        for action in (
            "list",
            "retrieve",
            "historico",
            "registrar_ocorrencia",
            "excluir_ocorrencia",
            "situacoes_disponiveis",
        ):
            with self.subTest(action=action):
                self.assertTrue(
                    perm.has_permission(self._request(user_gestor), self._view(action))
                )

        user_operador = self._user(operador=True)
        for action in (
            "list",
            "retrieve",
            "historico",
            "registrar_ocorrencia",
            "excluir_ocorrencia",
            "situacoes_disponiveis",
        ):
            with self.subTest(action=action):
                self.assertTrue(
                    perm.has_permission(self._request(user_operador), self._view(action))
                )

    def test_item_bloqueia_create_update_delete(self):
        perm = ItemConciliacaoPermission()
        user_gestor = self._user(gestor=True)

        for action in ("create", "update", "partial_update", "destroy"):
            with self.subTest(action=action):
                self.assertFalse(
                    perm.has_permission(self._request(user_gestor), self._view(action))
                )

    def test_item_has_object_permission_bloqueia_create_update_delete(self):
        perm = ItemConciliacaoPermission()
        user_gestor = self._user(gestor=True)
        obj = SimpleNamespace()

        for action in ("create", "update", "partial_update", "destroy"):
            with self.subTest(action=action):
                self.assertFalse(
                    perm.has_object_permission(
                        self._request(user_gestor), self._view(action), obj
                    )
                )

        for action in (
            "retrieve",
            "historico",
            "registrar_ocorrencia",
            "excluir_ocorrencia",
            "situacoes_disponiveis",
        ):
            with self.subTest(action=action):
                self.assertTrue(
                    perm.has_object_permission(
                        self._request(user_gestor), self._view(action), obj
                    )
                )
