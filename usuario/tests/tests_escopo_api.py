from dados_comuns.tests.auth_test_utils import auth_kwargs
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from rest_framework import status
from rest_framework.test import APITestCase
from itertools import count

from dados_comuns.models import HistoricoGeral, UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario


class EscopoEndpointsTestCase(APITestCase):
    _seq = count(1)

    def setUp(self):
        seq = next(self._seq)
        uo1_codigo = f"UO-{seq:04d}-A"
        uo2_codigo = f"UO-{seq:04d}-B"
        ua1_codigo = f"UA-{seq:04d}-1"
        ua2_codigo = f"UA-{seq:04d}-2"
        ua3_codigo = f"UA-{seq:04d}-3"

        self.uo1 = criar_uo(codigo=uo1_codigo, nome="UO 1")
        self.uo2 = criar_uo(codigo=uo2_codigo, nome="UO 2")

        self.ua1 = criar_ua(uo=self.uo1, codigo=ua1_codigo, sigla="UA1", nome="UA 1")
        self.ua2 = criar_ua(uo=self.uo1, codigo=ua2_codigo, sigla="UA2", nome="UA 2")
        self.ua3 = criar_ua(uo=self.uo2, codigo=ua3_codigo, sigla="UA3", nome="UA 3")

        self.grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        self.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

        self.gestor = Usuario.objects.create_user(
            username="gestor",
            email="gestor@teste.com",
            **auth_kwargs("test123"),
            nome="Gestor",
            is_staff=True,
            unidade_orcamentaria=self.uo1,
        )
        self.gestor.groups.add(self.grupo_gestor)

        self.operador = Usuario.objects.create_user(
            username="operador",
            email="operador@teste.com",
            **auth_kwargs("test123"),
            nome="Operador",
            is_staff=True,
            unidade_orcamentaria=self.uo1,
            unidade_administrativa=self.ua1,
        )
        self.operador.groups.add(self.grupo_operador)
        self.operador.unidades_administrativas.add(self.ua1)

        self.superuser = Usuario.objects.create_user(
            username="super",
            email="super@teste.com",
            **auth_kwargs("test123"),
            nome="Super",
            is_staff=True,
            is_superuser=True,
        )

        self.me_url = "/api/auth/me/"
        self.selecionar_ua_url = "/api/auth/me/selecionar-ua/"

    def test_me_opcoes_escopo_gestor(self):
        self.client.force_authenticate(user=self.gestor)
        resp = self.client.get(self.me_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        grupos = resp.data["opcoes_escopo"]["grupos"]
        self.assertEqual(len(grupos), 1)
        grupo = grupos[0]

        self.assertEqual(grupo["uo"]["id"], self.uo1.id)
        self.assertIsNone(grupo["uo"]["unidade_administrativa_id"])
        self.assertEqual(grupo["uo"]["unidade_orcamentaria_id"], self.uo1.id)
        uas = grupo["uas"]
        ua_ids = {ua["id"] for ua in uas}
        self.assertIn(self.ua1.id, ua_ids)
        self.assertIn(self.ua2.id, ua_ids)
        self.assertNotIn(self.ua3.id, ua_ids)

    def test_me_opcoes_escopo_operador(self):
        self.client.force_authenticate(user=self.operador)
        resp = self.client.get(self.me_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        grupos = resp.data["opcoes_escopo"]["grupos"]
        self.assertEqual(len(grupos), 1)
        grupo = grupos[0]

        self.assertEqual(grupo["uo"]["id"], self.uo1.id)
        self.assertIsNone(grupo["uo"]["unidade_administrativa_id"])
        self.assertEqual(grupo["uo"]["unidade_orcamentaria_id"], self.uo1.id)
        self.assertEqual(len(grupo["uas"]), 1)
        self.assertEqual(grupo["uas"][0]["id"], self.ua1.id)

    def test_me_opcoes_escopo_superuser(self):
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.get(self.me_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        grupos = resp.data["opcoes_escopo"]["grupos"]
        self.assertGreaterEqual(len(grupos), 2)

        grupos_por_uo = {grupo["uo"]["id"]: grupo for grupo in grupos}
        self.assertIn(self.uo1.id, grupos_por_uo)
        self.assertIn(self.uo2.id, grupos_por_uo)

        grupo_uo1 = grupos_por_uo[self.uo1.id]
        grupo_uo2 = grupos_por_uo[self.uo2.id]

        self.assertIsNone(grupo_uo1["uo"]["unidade_administrativa_id"])
        self.assertEqual(grupo_uo1["uo"]["unidade_orcamentaria_id"], self.uo1.id)
        self.assertIsNone(grupo_uo2["uo"]["unidade_administrativa_id"])
        self.assertEqual(grupo_uo2["uo"]["unidade_orcamentaria_id"], self.uo2.id)

        ua_ids_uo1 = {ua["id"] for ua in grupo_uo1["uas"]}
        ua_ids_uo2 = {ua["id"] for ua in grupo_uo2["uas"]}

        self.assertIn(self.ua1.id, ua_ids_uo1)
        self.assertIn(self.ua2.id, ua_ids_uo1)
        self.assertIn(self.ua3.id, ua_ids_uo2)

    def test_selecionar_ua_gestor(self):
        self.client.force_authenticate(user=self.gestor)
        resp = self.client.post(
            self.selecionar_ua_url,
            {"unidade_administrativa_id": self.ua2.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.gestor.refresh_from_db()
        self.assertEqual(self.gestor.unidade_administrativa_id, self.ua2.id)
        self.assertEqual(self.gestor.unidade_orcamentaria_id, self.uo1.id)

        ct = ContentType.objects.get_for_model(Usuario)
        historicos = HistoricoGeral.objects.filter(
            content_type=ct,
            object_id=str(self.gestor.pk),
            campo="unidade_administrativa",
        )
        self.assertTrue(historicos.exists())

    def test_selecionar_uo_gestor_limpa_ua(self):
        self.gestor.unidade_administrativa = self.ua1
        self.gestor.save(update_fields=["unidade_administrativa"])

        self.client.force_authenticate(user=self.gestor)
        resp = self.client.post(
            self.selecionar_ua_url,
            {
                "unidade_administrativa_id": None,
                "unidade_orcamentaria_id": self.uo1.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.gestor.refresh_from_db()
        self.assertIsNone(self.gestor.unidade_administrativa_id)

    def test_selecionar_uo_operador_nao_permitido(self):
        self.client.force_authenticate(user=self.operador)
        resp = self.client.post(
            self.selecionar_ua_url,
            {
                "unidade_administrativa_id": None,
                "unidade_orcamentaria_id": self.uo1.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_selecionar_ua_operador_sua_propria(self):
        self.client.force_authenticate(user=self.operador)
        resp = self.client.post(
            self.selecionar_ua_url,
            {"unidade_administrativa_id": self.ua1.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_selecionar_ua_gestor_outra_uo_nao_permitido(self):
        self.client.force_authenticate(user=self.gestor)
        resp = self.client.post(
            self.selecionar_ua_url,
            {"unidade_administrativa_id": self.ua3.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_selecionar_uo_superuser(self):
        self.client.force_authenticate(user=self.superuser)
        resp = self.client.post(
            self.selecionar_ua_url,
            {
                "unidade_administrativa_id": None,
                "unidade_orcamentaria_id": self.uo2.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.superuser.refresh_from_db()
        self.assertIsNone(self.superuser.unidade_administrativa_id)
        self.assertEqual(self.superuser.unidade_orcamentaria_id, self.uo2.id)

    def test_me_nao_exibe_ua_inativa(self):
        self.ua2.status = UnidadeAdministrativa.INATIVA
        self.ua2.save(update_fields=["status"])

        self.client.force_authenticate(user=self.gestor)
        resp = self.client.get(self.me_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        grupos = resp.data["opcoes_escopo"]["grupos"]
        grupo = grupos[0]
        ua_ids = {ua["id"] for ua in grupo["uas"]}
        self.assertNotIn(self.ua2.id, ua_ids)

    def test_me_nao_exibe_uo_inativa(self):
        self.uo2.ativa = False
        self.uo2.save(update_fields=["ativa"])

        self.client.force_authenticate(user=self.superuser)
        resp = self.client.get(self.me_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        grupos = resp.data["opcoes_escopo"]["grupos"]
        grupos_por_uo = {grupo["uo"]["id"] for grupo in grupos}
        self.assertNotIn(self.uo2.id, grupos_por_uo)

    def test_selecionar_ua_inativa_rejeita(self):
        self.ua2.status = UnidadeAdministrativa.INATIVA
        self.ua2.save(update_fields=["status"])

        self.client.force_authenticate(user=self.gestor)
        resp = self.client.post(
            self.selecionar_ua_url,
            {"unidade_administrativa_id": self.ua2.id},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_selecionar_uo_inativa_rejeita(self):
        self.uo2.ativa = False
        self.uo2.save(update_fields=["ativa"])

        self.client.force_authenticate(user=self.superuser)
        resp = self.client.post(
            self.selecionar_ua_url,
            {
                "unidade_administrativa_id": None,
                "unidade_orcamentaria_id": self.uo2.id,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
