from datetime import date
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from bem_patrimonial import constants as bem_constants
from bem_patrimonial.models import BemPatrimonial
from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua, codigo_uo
from dados_comuns.tests.factories import criar_ua, criar_uo
from inventario import constants
from inventario.models import ConciliacaoUA
from usuario.constants import (
    GRUPO_GESTOR_PATRIMONIO,
    GRUPO_OPERADOR_INVENTARIO,
)
from usuario.models import Usuario


class ConciliacaoUAAPITestCase(APITestCase):
    LIST_FIELDS = {
        "id",
        "numero_conciliacao",
        "unidade_administrativa",
        "unidade_administrativa_codigo",
        "unidade_administrativa_nome",
        "unidade_administrativa_sigla",
        "unidade_orcamentaria_codigo",
        "unidade_orcamentaria_nome",
        "tipo",
        "tipo_display",
        "periodo_final",
        "status",
        "status_display",
        "total_itens",
        "resumo_situacoes",
        "ano_vigencia",
        "criado_em",
        "fechado_em",
    }

    DETAIL_EXTRA_FIELDS = {
        "criado_por",
        "criado_por_nome",
        "criado_por_rf",
        "fechado_por",
        "fechado_por_nome",
        "fechado_por_rf",
        "esta_aberto",
    }

    @classmethod
    def setUpTestData(cls):
        cls.uo1 = criar_uo(codigo=codigo_uo(10, 10, 10), nome="UO 1", sigla="UO1")
        cls.uo2 = criar_uo(codigo=codigo_uo(20, 20, 20), nome="UO 2", sigla="UO2")

        cls.ua1 = criar_ua(
            uo=cls.uo1,
            codigo=codigo_ua(10, 10, 10, 1),
            sigla="UA1",
            nome="Unidade 1",
        )
        cls.ua2 = criar_ua(
            uo=cls.uo1,
            codigo=codigo_ua(10, 10, 10, 2),
            sigla="UA2",
            nome="Unidade 2",
        )
        cls.ua_fora = criar_ua(
            uo=cls.uo2,
            codigo=codigo_ua(20, 20, 20, 1),
            sigla="UAF",
            nome="Unidade Fora",
        )

        grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

        cls.gestor_com_ua = Usuario.objects.create_user(
            username="gestor_com_ua",
            email="gestor.com.ua@test.com",
            **auth_kwargs("test123"),
            nome="Gestor Com UA",
            is_staff=True,
            unidade_administrativa=cls.ua1,
            unidade_orcamentaria=cls.uo1,
        )
        cls.gestor_com_ua.groups.add(grupo_gestor)

        cls.gestor_sem_ua = Usuario.objects.create_user(
            username="gestor_sem_ua",
            email="gestor.sem.ua@test.com",
            **auth_kwargs("test123"),
            nome="Gestor Sem UA",
            is_staff=True,
            unidade_orcamentaria=cls.uo1,
        )
        cls.gestor_sem_ua.groups.add(grupo_gestor)

        cls.operador = Usuario.objects.create_user(
            username="operador",
            email="operador@test.com",
            **auth_kwargs("test123"),
            nome="Operador",
            is_staff=True,
            unidade_administrativa=cls.ua1,
            unidade_orcamentaria=cls.uo1,
        )
        cls.operador.groups.add(grupo_operador)

        cls.operador_fora = Usuario.objects.create_user(
            username="operador_fora",
            email="operador.fora@test.com",
            **auth_kwargs("test123"),
            nome="Operador Fora",
            is_staff=True,
            unidade_administrativa=cls.ua_fora,
            unidade_orcamentaria=cls.uo2,
        )
        cls.operador_fora.groups.add(grupo_operador)

        cls.superuser = Usuario.objects.create_user(
            username="superuser",
            email="superuser@test.com",
            **auth_kwargs("test123"),
            nome="Superuser",
            is_staff=True,
            is_superuser=True,
            unidade_orcamentaria=cls.uo1,
        )
        cls.superuser.groups.add(grupo_gestor)

    def setUp(self):
        self._criar_bem(self.ua1)
        self.conciliacao_ua1 = ConciliacaoUA.objects.create(
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=date(2025, 8, 23),
            unidade_administrativa=self.ua1,
            criado_por=self.gestor_com_ua,
        )
        self.conciliacao_ua2 = ConciliacaoUA.objects.create(
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=date(2025, 9, 1),
            unidade_administrativa=self.ua2,
            criado_por=self.gestor_com_ua,
        )
        self.conciliacao_fora = ConciliacaoUA.objects.create(
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=date(2025, 9, 1),
            unidade_administrativa=self.ua_fora,
            criado_por=self.operador_fora,
        )
        self.list_url = reverse("conciliacoes-list")

    def _criar_bem(self, ua, **kwargs):
        defaults = {
            "numero_patrimonial": f"001.{str(BemPatrimonial.objects.count() + 1).zfill(9)}-0",
            "nome": "Bem Teste",
            "descricao": "Descrição",
            "valor_unitario": Decimal("100.00"),
            "marca": "Marca",
            "modelo": "Modelo",
            "status": bem_constants.APROVADO,
            "unidade_administrativa": ua,
            "criado_por": self.gestor_com_ua,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def _auth(self, user):
        self.client.force_authenticate(user)

    def _detail_url(self, conciliacao_id):
        return reverse("conciliacoes-detail", args=[conciliacao_id])

    def _payload_create(self, **overrides):
        payload = {
            "unidade_administrativa": self.ua1.id,
            "tipo": constants.CONCILIACAO_EVENTUAL,
            "periodo_final": str(date.today()),
        }
        payload.update(overrides)
        return payload

    def test_nao_autenticado_retorna_401(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_operador_pode_listar(self):
        self._auth(self.operador)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.conciliacao_ua1.id, ids)
        self.assertNotIn(self.conciliacao_ua2.id, ids)
        self.assertNotIn(self.conciliacao_fora.id, ids)

    def test_gestor_com_ua_ve_apenas_sua_ua(self):
        self._auth(self.gestor_com_ua)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.conciliacao_ua1.id, ids)
        self.assertNotIn(self.conciliacao_ua2.id, ids)
        self.assertNotIn(self.conciliacao_fora.id, ids)

    def test_gestor_sem_ua_ve_uo_inteira(self):
        self._auth(self.gestor_sem_ua)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.conciliacao_ua1.id, ids)
        self.assertIn(self.conciliacao_ua2.id, ids)
        self.assertNotIn(self.conciliacao_fora.id, ids)

    def test_superuser_com_uo_ve_apenas_sua_uo(self):
        self._auth(self.superuser)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertIn(self.conciliacao_ua1.id, ids)
        self.assertIn(self.conciliacao_ua2.id, ids)
        self.assertNotIn(self.conciliacao_fora.id, ids)

    def test_listagem_campos_retorna_esperados(self):
        self._auth(self.gestor_com_ua)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data["results"][0].keys()), self.LIST_FIELDS
        )

    def test_listagem_filtros_status_tipo_e_ano(self):
        ConciliacaoUA.objects.filter(pk=self.conciliacao_ua2.pk).update(
            status=constants.CONCILIACAO_FECHADO
        )
        self._auth(self.gestor_sem_ua)

        response = self.client.get(
            self.list_url,
            {"status": constants.CONCILIACAO_FECHADO},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.conciliacao_ua2.id})

        response = self.client.get(
            self.list_url,
            {"tipo": constants.CONCILIACAO_EVENTUAL, "ano_vigencia": 2025},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(
            ids, {self.conciliacao_ua1.id, self.conciliacao_ua2.id}
        )

    def test_listagem_filtro_multi_status(self):
        ConciliacaoUA.objects.filter(pk=self.conciliacao_ua2.pk).update(
            status=constants.CONCILIACAO_FECHADO
        )
        self._auth(self.gestor_sem_ua)
        response = self.client.get(
            self.list_url,
            {
                "status": f"{constants.CONCILIACAO_EM_ABERTO},{constants.CONCILIACAO_FECHADO}"
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(
            ids, {self.conciliacao_ua1.id, self.conciliacao_ua2.id}
        )

    def test_listagem_filtro_periodo_final_range(self):
        self._auth(self.gestor_sem_ua)
        response = self.client.get(
            self.list_url,
            {
                "periodo_final__gte": "2025-08-01",
                "periodo_final__lte": "2025-08-31",
            },
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.conciliacao_ua1.id})

    def test_listagem_busca_por_numero(self):
        self._auth(self.gestor_sem_ua)
        response = self.client.get(
            self.list_url,
            {"search": self.conciliacao_ua1.numero_conciliacao},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.conciliacao_ua1.id})

    def test_listagem_ordenacao_criado_em_desc(self):
        self._auth(self.gestor_sem_ua)
        response = self.client.get(self.list_url, {"ordering": "-criado_em"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data["results"]]
        self.assertEqual(ids, sorted(ids, key=lambda x: -x))

    def test_retrieve_retorna_detalhe_completo(self):
        self._auth(self.gestor_com_ua)
        response = self.client.get(self._detail_url(self.conciliacao_ua1.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.conciliacao_ua1.id)
        self.assertTrue(
            self.DETAIL_EXTRA_FIELDS.issubset(set(response.data.keys()))
        )
        self.assertIn("encontrados", response.data["resumo_situacoes"])
        self.assertTrue(response.data["esta_aberto"])

    def test_retrieve_fora_do_escopo_retorna_404(self):
        self._auth(self.operador)
        response = self.client.get(self._detail_url(self.conciliacao_ua2.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_remove_itens_baixados_invalidos(self):
        from unittest.mock import patch

        self._auth(self.gestor_com_ua)
        with patch(
            "inventario.api_views.remover_itens_baixados_invalidos"
        ) as mock_remover:
            mock_remover.return_value = 0
            response = self.client.get(self._detail_url(self.conciliacao_ua1.id))
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            mock_remover.assert_called_once()

    def test_retrieve_conciliacao_fechada_nao_remove_itens(self):
        from unittest.mock import patch

        ConciliacaoUA.objects.filter(pk=self.conciliacao_ua1.pk).update(
            status=constants.CONCILIACAO_FECHADO
        )
        self._auth(self.gestor_com_ua)
        with patch(
            "inventario.api_views.remover_itens_baixados_invalidos"
        ) as mock_remover:
            response = self.client.get(self._detail_url(self.conciliacao_ua1.id))
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            mock_remover.assert_not_called()

    def test_create_eventual_por_gestor_com_ua(self):
        ConciliacaoUA.objects.filter(pk=self.conciliacao_ua1.pk).update(
            status=constants.CONCILIACAO_FECHADO
        )
        self._auth(self.gestor_com_ua)

        payload = self._payload_create(
            unidade_administrativa=self.ua1.id,
            periodo_final=str(date.today() + timezone.timedelta(days=10)),
        )
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["tipo"], constants.CONCILIACAO_EVENTUAL)
        self.assertEqual(response.data["unidade_administrativa"], self.ua1.id)
        nova = ConciliacaoUA.objects.get(pk=response.data["id"])
        self.assertEqual(nova.criado_por, self.gestor_com_ua)
        self.assertTrue(nova.itens.exists())

    def test_create_por_operador_no_escopo(self):
        ConciliacaoUA.objects.filter(pk=self.conciliacao_ua1.pk).update(
            status=constants.CONCILIACAO_FECHADO
        )
        self._auth(self.operador)
        payload = self._payload_create(
            periodo_final=str(date.today() + timezone.timedelta(days=10)),
        )
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["unidade_administrativa"], self.ua1.id)
        nova = ConciliacaoUA.objects.get(pk=response.data["id"])
        self.assertEqual(nova.criado_por, self.operador)
        self.assertTrue(nova.itens.exists())

    def test_create_sem_ua_fora_do_escopo_retorna_400(self):
        self._auth(self.gestor_com_ua)
        payload = self._payload_create(
            unidade_administrativa=self.ua_fora.id,
            periodo_final=str(date.today()),
        )
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unidade_administrativa", response.data)

    def test_create_tipo_anual_rejeitado(self):
        self._auth(self.gestor_com_ua)
        payload = self._payload_create(
            tipo=constants.CONCILIACAO_ANUAL,
            periodo_final="",
        )
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tipo", response.data)

    def test_create_eventual_sem_periodo_final_retorna_400(self):
        self._auth(self.gestor_sem_ua)
        payload = self._payload_create(
            unidade_administrativa=self.ua1.id,
            periodo_final="",
        )
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("periodo_final", response.data)

    def test_create_com_conciliacao_aberta_existente_retorna_400(self):
        self._auth(self.gestor_com_ua)
        payload = self._payload_create(
            periodo_final=str(date.today() + timezone.timedelta(days=10)),
        )
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unidade_administrativa", response.data)

    def test_create_por_operador_fora_do_escopo_retorna_400(self):
        self._auth(self.operador)
        payload = self._payload_create(
            unidade_administrativa=self.ua2.id,
            periodo_final=str(date.today()),
        )
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unidade_administrativa", response.data)

    def test_put_patch_delete_nao_permitidos(self):
        self._auth(self.gestor_com_ua)
        url = self._detail_url(self.conciliacao_ua1.id)

        put = self.client.put(
            url, self._payload_create(), format="json"
        )
        self.assertEqual(put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        patch = self.client.patch(url, {"status": "fechado"}, format="json")
        self.assertEqual(patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        delete = self.client.delete(url)
        self.assertEqual(delete.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_finalizar_por_gestor(self):
        self._auth(self.gestor_com_ua)
        url = reverse("conciliacoes-finalizar", args=[self.conciliacao_ua1.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.conciliacao_ua1.refresh_from_db()
        self.assertEqual(
            self.conciliacao_ua1.status, constants.CONCILIACAO_FECHADO
        )
        self.assertEqual(self.conciliacao_ua1.fechado_por, self.gestor_com_ua)

    def test_finalizar_ja_fechada_retorna_400(self):
        ConciliacaoUA.objects.filter(pk=self.conciliacao_ua1.pk).update(
            status=constants.CONCILIACAO_FECHADO
        )
        self._auth(self.gestor_com_ua)
        url = reverse("conciliacoes-finalizar", args=[self.conciliacao_ua1.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_finalizar_por_operador_no_escopo(self):
        self._auth(self.operador)
        url = reverse("conciliacoes-finalizar", args=[self.conciliacao_ua1.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.conciliacao_ua1.refresh_from_db()
        self.assertEqual(
            self.conciliacao_ua1.status, constants.CONCILIACAO_FECHADO
        )
        self.assertEqual(self.conciliacao_ua1.fechado_por, self.operador)

    def test_finalizar_fora_do_escopo_retorna_404(self):
        self._auth(self.gestor_com_ua)
        url = reverse("conciliacoes-finalizar", args=[self.conciliacao_fora.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_historico_retorna_grupos(self):
        self._auth(self.gestor_com_ua)
        url = reverse("conciliacoes-historico", args=[self.conciliacao_ua1.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)

    def test_historico_registra_finalizar(self):
        self._auth(self.gestor_com_ua)
        url_finalizar = reverse(
            "conciliacoes-finalizar", args=[self.conciliacao_ua1.id]
        )
        self.client.post(url_finalizar)

        url_historico = reverse(
            "conciliacoes-historico", args=[self.conciliacao_ua1.id]
        )
        response = self.client.get(url_historico)
        campos = {
            acao["campo"]
            for grupo in response.data
            for acao in grupo["acoes"]
        }
        self.assertIn("status", campos)
        self.assertIn("fechado_por", campos)

    def test_exportar_pdf_retorna_pdf(self):
        self._auth(self.gestor_com_ua)
        url = reverse("conciliacoes-exportar", args=[self.conciliacao_ua1.id])

        with patch(
            "inventario.api_views.gerar_pdf_conciliacao",
            return_value=BytesIO(b"%PDF-1.4\nconteudo\n%%EOF"),
        ):
            response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(".pdf", response["Content-Disposition"])

    def test_exportar_fora_do_escopo_retorna_404(self):
        self._auth(self.operador)
        url = reverse("conciliacoes-exportar", args=[self.conciliacao_ua2.id])

        with patch(
            "inventario.api_views.gerar_pdf_conciliacao",
            return_value=BytesIO(b"%PDF-1.4"),
        ):
            response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_exportar_conciliacao_inexistente_retorna_404(self):
        self._auth(self.gestor_com_ua)
        url = reverse("conciliacoes-exportar", args=[999999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_operador_fora_da_uo_nao_ve_nada(self):
        self._auth(self.operador_fora)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.conciliacao_fora.id})
