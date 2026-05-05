from unittest.mock import patch

from django.contrib.auth.models import Group
from django.db.models.deletion import ProtectedError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua, codigo_uo
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario


class UnidadeOrcamentariaAPITestCase(APITestCase):
    LIST_FIELDS = {
        "id",
        "codigo",
        "sigla",
        "nome",
        "ativa",
        "ativa_display",
    }

    def setUp(self):
        self.uo1 = criar_uo(codigo=codigo_uo(10, 10, 10), nome="UO 1", sigla="UO1")
        self.uo2 = criar_uo(
            codigo=codigo_uo(20, 20, 20),
            nome="UO 2",
            sigla="UO2",
            ativa=False,
        )
        self.uo3 = criar_uo(codigo=codigo_uo(30, 30, 30), nome="UO 3", sigla="UO3")

        self.uo_com_ua = criar_uo(
            codigo=codigo_uo(40, 40, 40),
            nome="UO Com UA",
            sigla="UOUA",
        )
        criar_ua(
            uo=self.uo_com_ua,
            codigo=codigo_ua(40, 40, 40, 1),
            sigla="UA40",
            nome="Unidade Vinculada",
        )

        self.uo_sem_vinculo = criar_uo(
            codigo=codigo_uo(50, 50, 50),
            nome="UO Sem Vinculo",
            sigla="UOLIVRE",
        )

        grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        grupo_operador = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)[0]

        self.gestor = Usuario.objects.create_user(
            username="gestor_uo_api",
            email="gestor.uo.api@test.com",
            **auth_kwargs("test123"),
            nome="Gestor UO",
            is_staff=True,
            unidade_orcamentaria=self.uo1,
        )
        self.gestor.groups.add(grupo_gestor)

        self.operador = Usuario.objects.create_user(
            username="operador_uo_api",
            email="operador.uo.api@test.com",
            **auth_kwargs("test123"),
            nome="Operador UO",
            is_staff=True,
            unidade_orcamentaria=self.uo1,
        )
        self.operador.groups.add(grupo_operador)

        self.superuser = Usuario.objects.create_user(
            username="super_uo_api",
            email="super.uo.api@test.com",
            **auth_kwargs("test123"),
            nome="Super UO",
            is_staff=True,
            is_superuser=True,
            unidade_orcamentaria=self.uo1,
        )

        self.list_url = reverse("unidades-orcamentarias-list")

    def _auth(self, user):
        self.client.force_authenticate(user)

    def _detail_url(self, uo_id):
        return reverse("unidades-orcamentarias-detail", args=[uo_id])

    def _payload_uo(self, **overrides):
        payload = {
            "codigo": codigo_uo(60, 60, 60),
            "sigla": "UO60",
            "nome": "UO 60",
            "ativa": True,
        }
        payload.update(overrides)
        return payload

    def test_nao_autenticado_retorna_401_no_get(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_apenas_superuser_acessa_modulo(self):
        cenarios = [self.gestor, self.operador]
        export_url = reverse("unidades-orcamentarias-exportar")
        historico_url = reverse("unidades-orcamentarias-historico", args=[self.uo1.id])

        for user in cenarios:
            with self.subTest(user=user.username):
                self._auth(user)

                self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_403_FORBIDDEN)
                self.assertEqual(
                    self.client.get(self._detail_url(self.uo1.id)).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.client.get(historico_url).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.client.get(export_url, {"formato": "csv"}).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.client.post(self.list_url, self._payload_uo(), format="json").status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.client.patch(
                        self._detail_url(self.uo1.id),
                        {"nome": "Alterada"},
                        format="json",
                    ).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.client.delete(self._detail_url(self.uo1.id)).status_code,
                    status.HTTP_403_FORBIDDEN,
                )

    def test_listagem_filtros_ordenacao_e_campos(self):
        self._auth(self.superuser)

        response = self.client.get(
            self.list_url,
            {"ativa": False, "search": "UO 2", "ordering": "-codigo"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self.uo2.id)
        self.assertEqual(set(response.data["results"][0].keys()), self.LIST_FIELDS)

        response_id = self.client.get(self.list_url, {"ordering": "-id"})
        ids = [row["id"] for row in response_id.data["results"]]
        self.assertEqual(ids, sorted(ids, reverse=True))

    def test_retrieve_criacao_atualizacao_e_historico(self):
        self._auth(self.superuser)

        detail = self.client.get(self._detail_url(self.uo1.id))
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data["id"], self.uo1.id)
        self.assertEqual(detail.data["ativa_display"], "Ativa")
        self.assertEqual(set(detail.data.keys()), self.LIST_FIELDS)

        create_response = self.client.post(
            self.list_url,
            self._payload_uo(codigo=codigo_uo(61, 61, 61), sigla="UO61", nome="UO 61"),
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)

        patch_response = self.client.patch(
            self._detail_url(self.uo1.id),
            {"nome": "UO 1 Alterada"},
            format="json",
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.data["nome"], "UO 1 Alterada")

        historico_response = self.client.get(
            reverse("unidades-orcamentarias-historico", args=[self.uo1.id]),
            {"search": "ignorar", "page": 99},
        )
        self.assertEqual(historico_response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(historico_response.data, list)
        self.assertGreaterEqual(len(historico_response.data), 1)
        self.assertIn("acoes", historico_response.data[0])
        self.assertTrue(
            any(
                acao["campo"] == "nome"
                for grupo in historico_response.data
                for acao in grupo["acoes"]
            )
        )

    def test_criacao_com_erro_de_validacao(self):
        self._auth(self.superuser)

        cenarios = [
            ({"codigo": "", "sigla": "UO", "nome": "Nome", "ativa": True}, "codigo"),
            ({"codigo": codigo_uo(70, 70, 70), "sigla": "UO", "nome": "", "ativa": True}, "nome"),
            ({"codigo": self.uo1.codigo, "sigla": "UO", "nome": "Duplicada", "ativa": True}, "codigo"),
        ]

        for payload, campo in cenarios:
            with self.subTest(campo=campo, payload=payload):
                response = self.client.post(self.list_url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(campo, response.data)

    def test_exportacao_por_formato_permitido(self):
        self._auth(self.superuser)
        formatos = {
            "csv": "text/csv",
            "xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "pdf": "application/pdf",
        }

        for formato, content_type in formatos.items():
            with self.subTest(formato=formato):
                response = self.client.get(
                    reverse("unidades-orcamentarias-exportar"),
                    {"formato": formato},
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response["Content-Type"], content_type)
                self.assertIn("attachment;", response["Content-Disposition"])

    def test_exportacao_parametro_invalido_retorna_400(self):
        self._auth(self.superuser)

        response = self.client.get(
            reverse("unidades-orcamentarias-exportar"),
            {"formato": "xml"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("formato", response.data)

    def test_delete_bloqueia_quando_existirem_unidades_administrativas_vinculadas(self):
        self._auth(self.superuser)

        response = self.client.delete(self._detail_url(self.uo_com_ua.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
        self.assertIn("unidades administrativas", response.data["detail"])

    def test_delete_bloqueia_quando_existirem_usuarios_vinculados(self):
        uo_com_usuario = criar_uo(
            codigo=codigo_uo(80, 80, 80),
            nome="UO Com Usuario",
            sigla="UOUSR",
        )
        Usuario.objects.create_user(
            username="usuario_vinculado_uo",
            email="usuario.vinculado.uo@test.com",
            **auth_kwargs("test123"),
            nome="Usuário Vinculado",
            unidade_orcamentaria=uo_com_usuario,
        )

        self._auth(self.superuser)
        response = self.client.delete(self._detail_url(uo_com_usuario.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
        self.assertIn("usuários", response.data["detail"])

    def test_delete_sem_vinculos_remove_uo(self):
        self._auth(self.superuser)

        response = self.client.delete(self._detail_url(self.uo_sem_vinculo.id))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        get_response = self.client.get(self._detail_url(self.uo_sem_vinculo.id))
        self.assertEqual(get_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_quando_protected_error_retorna_400(self):
        uo_livre = criar_uo(
            codigo=codigo_uo(90, 90, 90),
            nome="UO Livre",
            sigla="UOL",
        )

        self._auth(self.superuser)
        with patch(
            "dados_comuns.models.UnidadeOrcamentaria.delete",
            side_effect=ProtectedError("protegido", []),
        ):
            response = self.client.delete(self._detail_url(uo_livre.id))

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
