from dados_comuns.tests.auth_test_utils import auth_kwargs
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APITestCase

from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO
from usuario.filters import UsuarioFilter
from usuario.models import Usuario


class UsuarioFilterUnidadeAdministrativaIdTestCase(APITestCase):
    """
    Testes do novo parâmetro `unidade_administrativa_id` do UsuarioFilter,
    usado pela seção "Usuários Associados" na tela de visualização da
    Unidade Administrativa (usuário associado via FK ativa e via M2M).
    """

    def setUp(self):
        self.usuarios_url = "/api/user/"

        self.uo = criar_uo(codigo="UO-100", nome="UO Teste")
        self.ua1 = criar_ua(uo=self.uo, codigo="UA-100", sigla="UA1", nome="UA Um")
        self.ua2 = criar_ua(uo=self.uo, codigo="UA-200", sigla="UA2", nome="UA Dois")

        self.grupo_gestor = Group.objects.get_or_create(
            name=GRUPO_GESTOR_PATRIMONIO
        )[0]

        self.gestor = Usuario.objects.create_user(
            username="gestor_ua_filter",
            email="gestor_ua_filter@test.com",
            **auth_kwargs("test123"),
            nome="Gestor UA Filter",
            is_staff=True,
            unidade_orcamentaria=self.uo,
        )
        self.gestor.groups.add(self.grupo_gestor)

        # Usuário associado à UA1 apenas pela FK ativa.
        self.usuario_fk_ua1 = Usuario.objects.create_user(
            username="usuario_fk_ua1",
            email="usuario_fk_ua1@test.com",
            **auth_kwargs("test123"),
            nome="Usuário FK UA1",
            rf="1111111",
            unidade_orcamentaria=self.uo,
            unidade_administrativa=self.ua1,
        )

        # Usuário associado à UA2 apenas pela FK ativa.
        self.usuario_fk_ua2 = Usuario.objects.create_user(
            username="usuario_fk_ua2",
            email="usuario_fk_ua2@test.com",
            **auth_kwargs("test123"),
            nome="Usuário FK UA2",
            rf="2222222",
            unidade_orcamentaria=self.uo,
            unidade_administrativa=self.ua2,
        )

        # Usuário sem FK ativa em UA1, mas vinculado via M2M à UA1.
        self.usuario_m2m_ua1 = Usuario.objects.create_user(
            username="usuario_m2m_ua1",
            email="usuario_m2m_ua1@test.com",
            **auth_kwargs("test123"),
            nome="Usuário M2M UA1",
            rf="3333333",
            unidade_orcamentaria=self.uo,
        )
        self.usuario_m2m_ua1.unidades_administrativas.add(self.ua1)

        # Usuário sem qualquer vínculo com UA1 ou UA2.
        self.usuario_sem_vinculo = Usuario.objects.create_user(
            username="usuario_sem_vinculo",
            email="usuario_sem_vinculo@test.com",
            **auth_kwargs("test123"),
            nome="Usuário Sem Vínculo",
            rf="4444444",
            unidade_orcamentaria=self.uo,
        )

    def _listar(self, unidade_administrativa_id):
        self.client.force_authenticate(user=self.gestor)
        return self.client.get(
            self.usuarios_url,
            {"unidade_administrativa_id": unidade_administrativa_id},
        )

    def test_retorna_usuario_associado_via_fk(self):
        response = self._listar(self.ua1.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = {item["username"] for item in response.data["results"]}

        self.assertIn("usuario_fk_ua1", usernames)
        self.assertNotIn("usuario_fk_ua2", usernames)
        self.assertNotIn("usuario_sem_vinculo", usernames)

    def test_retorna_usuario_associado_via_m2m(self):
        response = self._listar(self.ua1.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = {item["username"] for item in response.data["results"]}

        self.assertIn("usuario_m2m_ua1", usernames)

    def test_nao_retorna_usuario_de_outra_ua(self):
        response = self._listar(self.ua2.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = {item["username"] for item in response.data["results"]}

        self.assertEqual(usernames, {"usuario_fk_ua2"})

    def test_retorna_lista_vazia_para_ua_sem_usuarios(self):
        ua_vazia = criar_ua(uo=self.uo, codigo="UA-300", sigla="UA3", nome="UA Vazia")

        response = self._listar(ua_vazia.id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["results"], [])
        self.assertEqual(response.data["count"], 0)

    def test_nao_retorna_registros_duplicados_quando_fk_e_m2m_coincidem(self):
        # Usuário associado à UA1 tanto pela FK ativa quanto pelo M2M:
        # deve aparecer apenas uma vez no resultado (distinct).
        self.usuario_fk_ua1.unidades_administrativas.add(self.ua1)

        response = self._listar(self.ua1.id)

        usernames = [item["username"] for item in response.data["results"]]
        self.assertEqual(usernames.count("usuario_fk_ua1"), 1)

    def test_sem_parametro_nao_aplica_filtro_de_ua(self):
        self.client.force_authenticate(user=self.gestor)
        response = self.client.get(self.usuarios_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        usernames = {item["username"] for item in response.data["results"]}

        # Sem o parâmetro, todos os usuários do escopo do gestor (mesma UO)
        # continuam sendo retornados normalmente.
        self.assertIn("usuario_fk_ua1", usernames)
        self.assertIn("usuario_fk_ua2", usernames)
        self.assertIn("usuario_sem_vinculo", usernames)

    def test_filtro_esta_registrado_no_meta_fields(self):
        self.assertIn("unidade_administrativa_id", UsuarioFilter.Meta.fields)
