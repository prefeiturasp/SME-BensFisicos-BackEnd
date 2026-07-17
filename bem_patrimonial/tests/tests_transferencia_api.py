from django.contrib.auth.models import Group
from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from bem_patrimonial import constants
from bem_patrimonial.models import (
    BemPatrimonial,
    TransferenciaBemPatrimonial,
    TransferenciaBensItem,
)
from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua, codigo_uo
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario


class TransferenciaApiTestCase(TestCase):
    def setUp(self):
        self.uo_origem = criar_uo(
            codigo=codigo_uo(1, 16, 28),
            nome="UO Origem",
            sigla="UOO",
        )
        self.ua_origem_1 = criar_ua(
            uo=self.uo_origem,
            codigo=f"{self.uo_origem.codigo}.001",
            sigla="UA1",
            nome="UA Origem 1",
        )
        self.ua_origem_2 = criar_ua(
            uo=self.uo_origem,
            codigo=f"{self.uo_origem.codigo}.002",
            sigla="UA2",
            nome="UA Origem 2",
        )
        self.uo_destino = criar_uo(
            codigo=codigo_uo(2, 20, 30),
            nome="Secretaria Externa",
            sigla="EXT",
        )
        self.ua_destino = criar_ua(
            uo=self.uo_destino,
            codigo=codigo_ua(2, 20, 30, 1),
            sigla="PC",
            nome="Ponto Central",
        )
        self.uo_destino_2 = criar_uo(
            codigo=codigo_uo(4, 40, 50),
            nome="Secretaria Externa 2",
            sigla="EXT2",
        )
        self.ua_destino_2 = criar_ua(
            uo=self.uo_destino_2,
            codigo=codigo_ua(4, 40, 50, 1),
            sigla="PC2",
            nome="Ponto Central 2",
        )
        self.uo_sem_pc = criar_uo(
            codigo=codigo_uo(3, 30, 40),
            nome="Secretaria Sem PC",
            sigla="SEMPC",
        )

        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)

        self.gestor = Usuario.objects.create_user(
            username="gestor_transfer_api",
            email="gestor.transfer.api@test.com",
            **auth_kwargs("123456"),
            nome="Gestor Transferência",
            is_staff=True,
            unidade_orcamentaria=self.uo_origem,
            unidade_administrativa=self.ua_origem_1,
        )
        self.gestor.groups.add(grupo_gestor)

        self.operador = Usuario.objects.create_user(
            username="operador_transfer_api",
            email="operador.transfer.api@test.com",
            **auth_kwargs("123456"),
            nome="Operador Transferência",
            is_staff=True,
            unidade_orcamentaria=self.uo_origem,
            unidade_administrativa=self.ua_origem_1,
        )
        self.operador.groups.add(grupo_operador)

        self.sem_permissao = Usuario.objects.create_user(
            username="sem_permissao_transfer_api",
            email="sem.permissao.transfer.api@test.com",
            **auth_kwargs("123456"),
            nome="Sem Permissão",
            is_staff=True,
            unidade_orcamentaria=self.uo_origem,
            unidade_administrativa=self.ua_origem_1,
        )

        self.bem_origem_1 = self._criar_bem(
            "001.000000001-1",
            self.ua_origem_1,
        )
        self.bem_origem_2 = self._criar_bem(
            "001.000000002-2",
            self.ua_origem_2,
        )
        self.bem_outra_uo = self._criar_bem(
            "002.000000001-1",
            criar_ua(
                uo=self.uo_destino,
                codigo=codigo_ua(2, 20, 30, 2),
                sigla="DST2",
                nome="Destino 2",
            ),
        )

        self.client = APIClient()

    def _autenticar(self, usuario):
        self.client.force_authenticate(user=usuario)

    def _criar_bem(self, numero_patrimonial, ua, status=constants.APROVADO):
        return BemPatrimonial.objects.create(
            numero_patrimonial=numero_patrimonial,
            nome=f"Bem {numero_patrimonial}",
            descricao="Bem para teste de transferência",
            valor_unitario=1000,
            marca="Dell",
            modelo="Latitude",
            numero_processo=f"PROC-{numero_patrimonial}",
            localizacao="Sala 1",
            criado_por=self.gestor,
            status=status,
            unidade_administrativa=ua,
        )

    def _criar_transferencia(self, numero_processo, uo_destino=None, ua_destino=None, bens=None):
        transferencia = TransferenciaBemPatrimonial.objects.create(
            unidade_orcamentaria_origem=self.uo_origem,
            unidade_orcamentaria_destino=uo_destino or self.uo_destino,
            unidade_administrativa_destino=ua_destino or self.ua_destino,
            numero_processo=numero_processo,
            observacao="Transferência teste",
            criado_por=self.gestor,
        )

        for bem in bens or [self.bem_origem_1]:
            TransferenciaBensItem.objects.create(
                transferencia=transferencia,
                bem=bem,
            )

        transferencia.efetivar_transferencia(self.gestor)
        transferencia.refresh_from_db()
        return transferencia

    def _lista_transferencias(self, response):
        if isinstance(response.data, dict) and "results" in response.data:
            return response.data["results"]
        return response.data

    def test_listagem_respeita_escopo_do_gestor(self):
        transfer_visivel = self._criar_transferencia("SEI-001/2026")

        outra_uo = criar_uo(
            codigo=codigo_uo(9, 9, 9),
            nome="Outra UO",
            sigla="OUT",
        )
        outra_ua = criar_ua(
            uo=outra_uo,
            codigo=codigo_ua(9, 9, 9, 1),
            sigla="OUT1",
            nome="Outra UA",
        )
        transferencia_oculta = TransferenciaBemPatrimonial.objects.create(
            unidade_orcamentaria_origem=outra_uo,
            unidade_orcamentaria_destino=self.uo_destino,
            unidade_administrativa_destino=self.ua_destino,
            numero_processo="SEI-999/2026",
            observacao="Fora do escopo",
            criado_por=self.gestor,
        )
        bem_fora_escopo = self._criar_bem("009.000000001-1", outra_ua)
        TransferenciaBensItem.objects.create(
            transferencia=transferencia_oculta,
            bem=bem_fora_escopo,
        )
        transferencia_oculta.efetivar_transferencia(self.gestor)
        transferencia_oculta.refresh_from_db()

        self._autenticar(self.gestor)
        response = self.client.get(reverse("transferencias-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in self._lista_transferencias(response)}
        self.assertIn(transfer_visivel.id, ids)
        self.assertNotIn(transferencia_oculta.id, ids)

    def test_opcoes_cadastro_trazem_apenas_uos_externas_com_ponto_central(self):
        url = reverse("transferencias-opcoes-cadastro")

        self._autenticar(self.gestor)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        uos = {item["id"]: item for item in response.data}
        self.assertIn(self.uo_destino.id, uos)
        self.assertNotIn(self.uo_origem.id, uos)
        self.assertTrue(uos[self.uo_destino.id]["tem_ponto_central"])

    def test_listagem_busca_por_numero_processo(self):
        transferencia_encontrada = self._criar_transferencia("SEI-001/2026")
        self._criar_transferencia(
            "SEI-002/2026",
            uo_destino=self.uo_destino_2,
            ua_destino=self.ua_destino_2,
            bens=[self.bem_origem_2],
        )

        self._autenticar(self.gestor)
        response = self.client.get(
            reverse("transferencias-list"),
            {"search": transferencia_encontrada.numero_processo},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        resultados = self._lista_transferencias(response)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(resultados[0]["numero_processo"], transferencia_encontrada.numero_processo)

    def test_listagem_filtra_por_uo_destino(self):
        transferencia_destino_2 = self._criar_transferencia(
            "SEI-003/2026",
            uo_destino=self.uo_destino_2,
            ua_destino=self.ua_destino_2,
            bens=[self.bem_origem_2],
        )
        self._criar_transferencia("SEI-004/2026")

        self._autenticar(self.gestor)
        response = self.client.get(
            reverse("transferencias-list"),
            {"unidade_orcamentaria_destino": self.uo_destino_2.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        resultados = self._lista_transferencias(response)
        ids = {item["id"] for item in resultados}
        self.assertIn(transferencia_destino_2.id, ids)
        self.assertNotIn(self.uo_destino.id, {item["unidade_orcamentaria_destino"]["id"] for item in resultados})
        self.assertTrue(all(item["unidade_orcamentaria_destino"]["id"] == self.uo_destino_2.id for item in resultados))

    def test_listagem_paginada_respeita_page_size(self):
        primeira = self._criar_transferencia("SEI-005/2026")
        segunda = self._criar_transferencia(
            "SEI-006/2026",
            uo_destino=self.uo_destino_2,
            ua_destino=self.ua_destino_2,
            bens=[self.bem_origem_2],
        )

        self._autenticar(self.gestor)
        response = self.client.get(
            reverse("transferencias-list"),
            {"page_size": 1},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNotNone(response.data["next"])
        self.assertEqual(response.data["results"][0]["id"], segunda.id)
        self.assertNotEqual(response.data["results"][0]["id"], primeira.id)

    def test_usuario_sem_permissao_nao_acessa_api(self):
        self._autenticar(self.sem_permissao)
        response = self.client.get(reverse("transferencias-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_operador_nao_acessa_api_de_transferencia(self):
        self._autenticar(self.operador)
        response = self.client.get(reverse("transferencias-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_transferencia_transfere_bens_e_gera_ntbpm(self):
        self._autenticar(self.gestor)
        payload = {
            "unidade_orcamentaria_destino": self.uo_destino.id,
            "numero_processo": "SEI-123456/2026",
            "observacao": "Transferência criada pela API",
            "itens": [
                {"bem": self.bem_origem_1.id},
                {"bem": self.bem_origem_2.id},
            ],
        }

        response = self.client.post(reverse("transferencias-list"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        transferencia = TransferenciaBemPatrimonial.objects.get(pk=response.data["id"])
        self.assertTrue(response.data["numero_ntbpm"])
        self.assertEqual(transferencia.numero_ntbpm, response.data["numero_ntbpm"])
        self.assertEqual(
            transferencia.unidade_administrativa_destino_id,
            self.ua_destino.id,
        )

        self.bem_origem_1.refresh_from_db()
        self.bem_origem_2.refresh_from_db()
        self.assertEqual(self.bem_origem_1.status, constants.TRANSFERIDO)
        self.assertEqual(self.bem_origem_2.status, constants.TRANSFERIDO)
        self.assertEqual(self.bem_origem_1.unidade_administrativa_id, self.ua_destino.id)
        self.assertEqual(self.bem_origem_2.unidade_administrativa_id, self.ua_destino.id)
        self.assertTrue(response.data["url_documento_ntbpm"])
        self.assertIn(str(transferencia.pk), response.data["url_documento_ntbpm"])

    def test_create_rejeita_bem_sem_status_aprovado(self):
        bem_bloqueado = self._criar_bem(
            "001.000000009-9",
            self.ua_origem_1,
            status=constants.BLOQUEADO,
        )

        self._autenticar(self.gestor)
        payload = {
            "unidade_orcamentaria_destino": self.uo_destino.id,
            "numero_processo": "SEI-123457/2026",
            "observacao": "Transferencia com bem nao aprovado",
            "itens": [{"bem": bem_bloqueado.id}],
        }

        response = self.client.post(reverse("transferencias-list"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("itens", response.data)
        self.assertIn("status 'Aprovado'", str(response.data["itens"]))

    def test_create_rejeita_bem_fora_da_uo_origem(self):
        self._autenticar(self.gestor)
        payload = {
            "unidade_orcamentaria_destino": self.uo_destino.id,
            "numero_processo": "SEI-123458/2026",
            "observacao": "Transferencia com bem fora da UO",
            "itens": [{"bem": self.bem_outra_uo.id}],
        }

        response = self.client.post(reverse("transferencias-list"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("itens", response.data)
        self.assertIn("não pertence à UO de origem", str(response.data["itens"]))

    def test_create_rejeita_uo_interna_da_sme(self):
        self._autenticar(self.gestor)
        payload = {
            "unidade_orcamentaria_destino": self.uo_origem.id,
            "numero_processo": "SEI-123456/2026",
            "observacao": "Transferência inválida",
            "itens": [{"bem": self.bem_origem_1.id}],
        }

        response = self.client.post(reverse("transferencias-list"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unidade_orcamentaria_destino", response.data)

    def test_create_rejeita_uo_sem_ponto_central(self):
        ua_sem_pc = criar_ua(
            uo=self.uo_sem_pc,
            codigo=codigo_ua(3, 30, 40, 2),
            sigla="DST",
            nome="Destino sem PC",
        )
        self._autenticar(self.gestor)
        payload = {
            "unidade_orcamentaria_destino": self.uo_sem_pc.id,
            "numero_processo": "SEI-654321/2026",
            "observacao": "Transferência inválida",
            "itens": [{"bem": self.bem_origem_1.id}],
        }

        response = self.client.post(reverse("transferencias-list"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unidade_orcamentaria_destino", response.data)
        self.assertIn("ponto central", str(response.data["unidade_orcamentaria_destino"]).lower())
        self.assertEqual(ua_sem_pc.unidade_orcamentaria_id, self.uo_sem_pc.id)

    def test_retrieve_exibe_url_documento_ntbpm(self):
        transferencia = self._criar_transferencia(
            "SEI-777/2026",
            bens=[self.bem_origem_1, self.bem_origem_2],
        )

        self._autenticar(self.gestor)
        response = self.client.get(
            reverse("transferencias-detail", kwargs={"pk": transferencia.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], transferencia.id)
        self.assertTrue(response.data["url_documento_ntbpm"])
        self.assertIn(str(transferencia.pk), response.data["url_documento_ntbpm"])
        self.assertEqual(len(response.data["itens"]), 2)
        self.assertEqual(response.data["total_itens"], 2)
