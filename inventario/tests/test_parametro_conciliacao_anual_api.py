from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.db.models.deletion import ProtectedError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from dados_comuns.tests.auth_test_utils import auth_kwargs
from dados_comuns.tests.factories import criar_uo
from inventario.models import ParametroConciliacaoAnual
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario


class ParametroConciliacaoAnualAPITestCase(APITestCase):
    RESPONSE_FIELDS = {
        "id",
        "unidade_orcamentaria",
        "unidade_orcamentaria_codigo",
        "unidade_orcamentaria_nome",
        "unidade_orcamentaria_sigla",
        "ano_referencia",
        "periodo_inicial",
        "periodo_final",
        "ativo",
        "esta_vigente",
    }

    def setUp(self):
        self.uo1 = criar_uo(codigo="10.10.10", nome="UO 1", sigla="UO1")
        self.uo2 = criar_uo(codigo="20.20.20", nome="UO 2", sigla="UO2")

        self.parametro1 = ParametroConciliacaoAnual.objects.create(
            unidade_orcamentaria=self.uo1,
            ano_referencia=2025,
            periodo_inicial=date(2026, 1, 1),
            periodo_final=date(2026, 3, 31),
            ativo=True,
        )
        self.parametro2 = ParametroConciliacaoAnual.objects.create(
            unidade_orcamentaria=self.uo1,
            ano_referencia=2024,
            periodo_inicial=date(2025, 1, 1),
            periodo_final=date(2025, 3, 31),
            ativo=False,
        )
        self.parametro3 = ParametroConciliacaoAnual.objects.create(
            unidade_orcamentaria=self.uo2,
            ano_referencia=2023,
            periodo_inicial=date(2024, 1, 1),
            periodo_final=date(2024, 3, 31),
            ativo=True,
        )

        grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        grupo_operador = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)[0]

        self.gestor = Usuario.objects.create_user(
            username="gestor_parametro_api",
            email="gestor.parametro.api@test.com",
            **auth_kwargs("test123"),
            nome="Gestor Parametro",
            is_staff=True,
            unidade_orcamentaria=self.uo1,
        )
        self.gestor.groups.add(grupo_gestor)

        self.operador = Usuario.objects.create_user(
            username="operador_parametro_api",
            email="operador.parametro.api@test.com",
            **auth_kwargs("test123"),
            nome="Operador Parametro",
            is_staff=True,
            unidade_orcamentaria=self.uo1,
        )
        self.operador.groups.add(grupo_operador)

        self.superuser = Usuario.objects.create_user(
            username="super_parametro_api",
            email="super.parametro.api@test.com",
            **auth_kwargs("test123"),
            nome="Super Parametro",
            is_staff=True,
            is_superuser=True,
            unidade_orcamentaria=self.uo1,
        )

        self.list_url = reverse("parametros-conciliacao-anual-list")

    def _auth(self, user):
        self.client.force_authenticate(user)

    def _payload_parametro(
        self,
        *,
        unidade_orcamentaria,
        ano_referencia=2022,
        periodo_inicial="2023-01-01",
        periodo_final="2023-03-31",
        ativo=True,
    ):
        return {
            "unidade_orcamentaria": unidade_orcamentaria,
            "ano_referencia": ano_referencia,
            "periodo_inicial": periodo_inicial,
            "periodo_final": periodo_final,
            "ativo": ativo,
        }

    def _detail_url(self, parametro_id):
        return reverse("parametros-conciliacao-anual-detail", args=[parametro_id])

    def _assert_response_fields(self, payload):
        self.assertEqual(set(payload.keys()), self.RESPONSE_FIELDS)

    def _post_parametro(self, **payload_overrides):
        payload = self._payload_parametro(
            unidade_orcamentaria=self.uo1.id,
            **payload_overrides,
        )
        return self.client.post(self.list_url, payload, format="json")

    def _assert_bad_request(self, response):
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(
            "non_field_errors" in response.data
            or "periodo_final" in response.data
        )

    def test_nao_autenticado_retorna_401_no_get(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_listagem_respeita_escopo_por_perfil(self):
        cenarios = [
            (self.gestor, {self.parametro1.id, self.parametro2.id}, {self.parametro3.id}),
            (self.operador, {self.parametro1.id, self.parametro2.id}, {self.parametro3.id}),
            (self.superuser, {self.parametro1.id, self.parametro2.id}, {self.parametro3.id}),
        ]

        for user, deve_ter, nao_deve_ter in cenarios:
            with self.subTest(user=user.username):
                self._auth(user)
                response = self.client.get(self.list_url)
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                ids = {row["id"] for row in response.data["results"]}
                self.assertTrue(deve_ter.issubset(ids))
                self.assertTrue(ids.isdisjoint(nao_deve_ter))
                self._assert_response_fields(response.data["results"][0])

    def test_listagem_filtros_ordenacao_e_busca(self):
        self._auth(self.gestor)

        response = self.client.get(
            self.list_url,
            {"ativo": True, "ano_referencia": 2025, "search": "10.10", "ordering": "-ano_referencia"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self.parametro1.id)

    def test_retrieve_respeita_escopo(self):
        self._auth(self.gestor)

        ok = self.client.get(self._detail_url(self.parametro1.id))
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(ok.data["id"], self.parametro1.id)
        self._assert_response_fields(ok.data)

        fora_escopo = self.client.get(self._detail_url(self.parametro3.id))
        self.assertEqual(fora_escopo.status_code, status.HTTP_404_NOT_FOUND)

    def test_criacao_por_gestor(self):
        self._auth(self.gestor)

        response = self.client.post(
            self.list_url,
            self._payload_parametro(unidade_orcamentaria=self.uo1.id),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["ano_referencia"], 2022)
        self.assertEqual(response.data["unidade_orcamentaria"], self.uo1.id)

    def test_criacao_nao_permite_sobreposicao_de_periodos(self):
        self._auth(self.gestor)

        cenarios = (
            {"ano_referencia": 2025},
            {"ano_referencia": 2026},
        )
        for payload in cenarios:
            with self.subTest(**payload):
                response = self._post_parametro(
                    **payload,
                    periodo_inicial="2026-02-01",
                    periodo_final="2026-04-30",
                    ativo=False,
                )
                self._assert_bad_request(response)

    def test_criacao_permite_mesmo_ano_em_outra_uo(self):
        self._auth(self.superuser)

        response = self.client.post(
            self.list_url,
            self._payload_parametro(
                unidade_orcamentaria=self.uo2.id,
                ano_referencia=2025,
                periodo_inicial="2026-01-01",
                periodo_final="2026-03-31",
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["unidade_orcamentaria"], self.uo2.id)

    def test_superuser_pode_criar_em_qualquer_uo(self):
        self._auth(self.superuser)

        response = self.client.post(
            self.list_url,
            self._payload_parametro(
                unidade_orcamentaria=self.uo2.id,
                ano_referencia=2022,
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["unidade_orcamentaria"], self.uo2.id)

    def test_operador_nao_pode_criar_editar_excluir(self):
        self._auth(self.operador)

        create_resp = self.client.post(
            self.list_url,
            self._payload_parametro(unidade_orcamentaria=self.uo1.id),
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_403_FORBIDDEN)

        patch_resp = self.client.patch(
            self._detail_url(self.parametro1.id),
            {"ativo": False},
            format="json",
        )
        self.assertEqual(patch_resp.status_code, status.HTTP_403_FORBIDDEN)

        delete_resp = self.client.delete(self._detail_url(self.parametro1.id))
        self.assertEqual(delete_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_e_put_atualizam_parametro(self):
        self._auth(self.gestor)

        patch_response = self.client.patch(
            self._detail_url(self.parametro2.id),
            {"ativo": True, "ano_referencia": 2024},
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertTrue(patch_response.data["ativo"])

        put_response = self.client.put(
            self._detail_url(self.parametro2.id),
            self._payload_parametro(
                unidade_orcamentaria=self.uo1.id,
                ano_referencia=2024,
                periodo_inicial="2025-04-01",
                periodo_final="2025-06-30",
                ativo=False,
            ),
            format="json",
        )
        self.assertEqual(put_response.status_code, status.HTTP_200_OK)
        self.assertEqual(put_response.data["periodo_inicial"], "2025-04-01")
        self.assertFalse(put_response.data["ativo"])

    def test_patch_nao_permite_gerenciar_uo_fora_do_escopo(self):
        self._auth(self.gestor)

        response = self.client.patch(
            self._detail_url(self.parametro1.id),
            {"unidade_orcamentaria": self.uo2.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unidade_orcamentaria", response.data)

    def test_delete_exclui_registro(self):
        extra = ParametroConciliacaoAnual.objects.create(
            unidade_orcamentaria=self.uo1,
            ano_referencia=2021,
            periodo_inicial=date(2022, 1, 1),
            periodo_final=date(2022, 3, 31),
            ativo=False,
        )

        self._auth(self.gestor)
        response = self.client.delete(self._detail_url(extra.id))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_delete_quando_protected_error_retorna_400(self):
        self._auth(self.gestor)

        with patch(
            "inventario.api_views.ParametroConciliacaoAnual.delete",
            side_effect=ProtectedError("protegido", []),
        ):
            response = self.client.delete(self._detail_url(self.parametro1.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
