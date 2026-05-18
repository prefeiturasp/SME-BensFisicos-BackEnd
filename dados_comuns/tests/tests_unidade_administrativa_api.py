from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua, codigo_uo
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.db.models.deletion import ProtectedError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario


class UnidadeAdministrativaAPITestCase(APITestCase):
    LIST_FIELDS = {
        "id",
        "codigo",
        "sigla",
        "nome",
        "status",
        "status_display",
        "unidade_orcamentaria",
        "unidade_orcamentaria_codigo",
        "unidade_orcamentaria_nome",
        "unidade_orcamentaria_sigla",
        "created_at",
        "updated_at",
    }

    def setUp(self):
        self.uo1 = criar_uo(codigo=codigo_uo(10, 10, 10), nome="UO 1")
        self.uo2 = criar_uo(codigo=codigo_uo(20, 20, 20), nome="UO 2")

        self.ua1 = criar_ua(
            uo=self.uo1,
            codigo=codigo_ua(10, 10, 10, 1),
            sigla="UA1",
            nome="Unidade 1",
            status=UnidadeAdministrativa.ATIVA,
        )
        self.ua2 = criar_ua(
            uo=self.uo1,
            codigo=codigo_ua(10, 10, 10, 2),
            sigla="UA2",
            nome="Unidade 2",
            status=UnidadeAdministrativa.INATIVA,
        )
        self.ua3 = criar_ua(
            uo=self.uo2,
            codigo=codigo_ua(20, 20, 20, 3),
            sigla="UA3",
            nome="Unidade 3",
            status=UnidadeAdministrativa.ATIVA,
        )

        grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        grupo_operador = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)[0]

        self.gestor = Usuario.objects.create_user(
            username="gestor_ua_api",
            email="gestor.ua.api@test.com",
            **auth_kwargs("test123"),
            nome="Gestor UA",
            is_staff=True,
            unidade_orcamentaria=self.uo1,
        )
        self.gestor.groups.add(grupo_gestor)

        self.operador = Usuario.objects.create_user(
            username="operador_ua_api",
            email="operador.ua.api@test.com",
            **auth_kwargs("test123"),
            nome="Operador UA",
            is_staff=True,
            unidade_orcamentaria=self.uo1,
            unidade_administrativa=self.ua1,
        )
        self.operador.groups.add(grupo_operador)

        self.superuser = Usuario.objects.create_user(
            username="super_ua_api",
            email="super.ua.api@test.com",
            **auth_kwargs("test123"),
            nome="Super UA",
            is_staff=True,
            is_superuser=True,
            unidade_orcamentaria=self.uo1,
        )

        self.list_url = reverse("unidades-administrativas-list")

    def _auth(self, user):
        self.client.force_authenticate(user)

    def _payload_ua(self, *, uo_id, codigo=None, sigla="UA", nome="Unidade", status_="ativa"):
        payload = {
            "unidade_orcamentaria": uo_id,
            "sigla": sigla,
            "nome": nome,
            "status": status_,
        }
        if codigo is not None:
            payload["codigo"] = codigo
        return payload

    def _assert_response_fields(self, payload):
        self.assertEqual(set(payload.keys()), self.LIST_FIELDS)

    def _get_detail_url(self, ua_id):
        return reverse("unidades-administrativas-detail", args=[ua_id])

    def test_nao_autenticado_retorna_401_no_get(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_listagem_respeita_escopo_por_perfil(self):
        cenarios = [
            (self.gestor, {self.ua1.id, self.ua2.id}, {self.ua3.id}),
            (self.operador, {self.ua1.id, self.ua2.id}, {self.ua3.id}),
            (self.superuser, {self.ua1.id, self.ua2.id}, {self.ua3.id}),
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

    def test_listagem_filtros_ordenacao_e_campos(self):
        self._auth(self.gestor)

        response = self.client.get(
            self.list_url,
            {
                "status": UnidadeAdministrativa.ATIVA,
                "search": "Unidade 1",
                "ordering": "-codigo",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["id"], self.ua1.id)
        self.assertIn("unidade_orcamentaria_sigla", response.data["results"][0])

        response_id = self.client.get(self.list_url, {"ordering": "-id"})
        ids = [row["id"] for row in response_id.data["results"]]
        self.assertEqual(ids, sorted(ids, reverse=True))

    def test_retrieve_campos_completos_e_escopo(self):
        self._auth(self.gestor)

        ok = self.client.get(self._get_detail_url(self.ua1.id))
        self.assertEqual(ok.status_code, status.HTTP_200_OK)
        self.assertEqual(ok.data["id"], self.ua1.id)
        self.assertEqual(ok.data["status_display"], "Ativa")
        self.assertEqual(ok.data["unidade_orcamentaria_sigla"], self.uo1.sigla)
        self._assert_response_fields(ok.data)

        fora_escopo = self.client.get(self._get_detail_url(self.ua3.id))
        self.assertEqual(fora_escopo.status_code, status.HTTP_404_NOT_FOUND)

        self._auth(self.superuser)
        ok_super = self.client.get(self._get_detail_url(self.ua1.id))
        self.assertEqual(ok_super.status_code, status.HTTP_200_OK)

        fora_escopo_super = self.client.get(self._get_detail_url(self.ua3.id))
        self.assertEqual(fora_escopo_super.status_code, status.HTTP_404_NOT_FOUND)

    def test_parametro_unidade_orcamentaria_nao_altera_escopo(self):
        self._auth(self.gestor)
        response = self.client.get(self.list_url, {"unidade_orcamentaria": self.uo2.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.ua1.id, self.ua2.id})

    def test_criacao_codigo_valido_em_varios_formatos(self):
        self._auth(self.gestor)
        cenarios = [
            ("050", codigo_ua(10, 10, 10, 50)),
            ("1002", f"{codigo_uo(10, 10, 10)}.1002"),
            (codigo_ua(10, 10, 10, 777), codigo_ua(10, 10, 10, 777)),
        ]

        for codigo_in, codigo_out in cenarios:
            with self.subTest(codigo=codigo_in):
                response = self.client.post(
                    self.list_url,
                    self._payload_ua(
                        uo_id=self.uo1.id,
                        codigo=codigo_in,
                        sigla=f"UA{codigo_in}",
                        nome=f"Unidade {codigo_in}",
                    ),
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)
                self.assertEqual(response.data["codigo"], codigo_out)

    def test_criacao_com_erro_de_validacao(self):
        self._auth(self.gestor)

        cenarios = [
            (self._payload_ua(uo_id=self.uo1.id, codigo=None), "codigo"),
            (self._payload_ua(uo_id=self.uo1.id, codigo="AB12"), "codigo"),
            (
                self._payload_ua(uo_id=self.uo2.id, codigo=codigo_ua(20, 20, 20, 50)),
                "unidade_orcamentaria",
            ),
        ]

        for payload, campo_esperado in cenarios:
            with self.subTest(campo=campo_esperado, payload=payload):
                response = self.client.post(self.list_url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(campo_esperado, response.data)

    def test_post_nao_permite_codigo_duplicado(self):
        self._auth(self.gestor)

        response = self.client.post(
            self.list_url,
            self._payload_ua(
                uo_id=self.uo1.id,
                codigo="001",
                sigla="UA DUP",
                nome="Unidade Duplicada",
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("codigo", response.data)

    def test_patch_nao_permite_codigo_duplicado(self):
        self._auth(self.gestor)

        response = self.client.patch(
            self._get_detail_url(self.ua2.id),
            {"codigo": "001"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("codigo", response.data)

    def test_put_nao_permite_codigo_duplicado(self):
        self._auth(self.gestor)

        response = self.client.put(
            self._get_detail_url(self.ua2.id),
            self._payload_ua(
                uo_id=self.uo1.id,
                codigo="001",
                sigla="UA2",
                nome="Unidade 2",
                status_=UnidadeAdministrativa.INATIVA,
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("codigo", response.data)

    def test_superuser_pode_criar_em_qualquer_uo(self):
        self._auth(self.superuser)
        response = self.client.post(
            self.list_url,
            self._payload_ua(
                uo_id=self.uo2.id,
                codigo="090",
                sigla="UA90",
                nome="UA do Superuser",
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["unidade_orcamentaria"], self.uo2.id)
        self.assertEqual(response.data["codigo"], codigo_ua(20, 20, 20, 90))

    def test_operador_nao_pode_criar_editar_excluir(self):
        self._auth(self.operador)

        create_resp = self.client.post(
            self.list_url,
            self._payload_ua(
                uo_id=self.uo1.id,
                codigo="060",
                sigla="UA60",
                nome="Unidade Sem Permissao",
            ),
            format="json",
        )
        self.assertEqual(create_resp.status_code, status.HTTP_403_FORBIDDEN)

        detail_url = self._get_detail_url(self.ua1.id)
        patch_resp = self.client.patch(detail_url, {"nome": "Nome Alterado"}, format="json")
        self.assertEqual(patch_resp.status_code, status.HTTP_403_FORBIDDEN)

        delete_resp = self.client.delete(detail_url)
        self.assertEqual(delete_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_troca_uo_com_codigo_legado_invalido_rejeita(self):
        ua_legado = criar_ua(
            uo=self.uo1,
            codigo="CODIGO-LEGADO",
            sigla="UAL",
            nome="UA Legado",
            status=UnidadeAdministrativa.ATIVA,
        )

        self._auth(self.superuser)
        response = self.client.patch(
            self._get_detail_url(ua_legado.id),
            {"unidade_orcamentaria": self.uo2.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("codigo", response.data)

    def test_historico_retorna_lista_e_ignora_filtros(self):
        self._auth(self.gestor)
        detail_url = self._get_detail_url(self.ua1.id)
        patch_resp = self.client.patch(detail_url, {"nome": "Unidade 1 Alterada"}, format="json")
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)

        historico_url = reverse("unidades-administrativas-historico", args=[self.ua1.id])
        response = self.client.get(
            historico_url,
            {
                "search": "abc",
                "ordering": "-id",
                "status": UnidadeAdministrativa.INATIVA,
                "page": 10,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        self.assertGreaterEqual(len(response.data), 1)
        self.assertIn("acoes", response.data[0])

        self._auth(self.superuser)
        historico_fora_escopo = self.client.get(
            reverse("unidades-administrativas-historico", args=[self.ua3.id])
        )
        self.assertEqual(historico_fora_escopo.status_code, status.HTTP_404_NOT_FOUND)

    def test_exportacao_por_formato_permitido(self):
        self._auth(self.gestor)
        formatos = {
            "csv": "text/csv",
            "xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "pdf": "application/pdf",
        }

        for formato, content_type in formatos.items():
            with self.subTest(formato=formato):
                response = self.client.get(
                    reverse("unidades-administrativas-exportar"),
                    {"formato": formato},
                )
                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response["Content-Type"], content_type)
                self.assertIn("attachment;", response["Content-Disposition"])

    def test_exportacao_superuser_respeita_escopo_ativo(self):
        self._auth(self.superuser)

        response = self.client.get(
            reverse("unidades-administrativas-exportar"),
            {"formato": "csv"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        conteudo = response.content.decode("utf-8-sig")
        self.assertIn(self.ua1.codigo, conteudo)
        self.assertIn(self.ua2.codigo, conteudo)
        self.assertNotIn(self.ua3.codigo, conteudo)

    def test_exportacao_validacoes_e_permissoes(self):
        self._auth(self.operador)
        bloqueado = self.client.get(reverse("unidades-administrativas-exportar"), {"formato": "csv"})
        self.assertEqual(bloqueado.status_code, status.HTTP_403_FORBIDDEN)

        self._auth(self.gestor)
        invalido = self.client.get(reverse("unidades-administrativas-exportar"), {"formato": "xml"})
        self.assertEqual(invalido.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("formato", invalido.data)

    def test_delete_quando_protected_error_retorna_400(self):
        self._auth(self.gestor)
        detail_url = self._get_detail_url(self.ua1.id)

        with patch.object(
            UnidadeAdministrativa,
            "delete",
            side_effect=ProtectedError("protegido", []),
        ):
            response = self.client.delete(detail_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
