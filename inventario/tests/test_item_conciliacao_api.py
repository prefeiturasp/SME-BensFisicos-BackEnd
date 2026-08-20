from django.urls import reverse
from rest_framework import status

from inventario import constants
from inventario.models import ItemConciliacao, OcorrenciaConciliacao
from inventario.tests.conciliacao_base import ConciliacaoAPIBaseTestCase


class ItemConciliacaoAPITestCase(ConciliacaoAPIBaseTestCase):
    username_prefix = "items_"

    LIST_FIELDS = {
        "id",
        "conciliacao",
        "conciliacao_numero",
        "conciliacao_status",
        "unidade_administrativa",
        "unidade_administrativa_sigla",
        "bem",
        "situacao",
        "situacao_display",
        "observacao",
        "divergencia",
        "tem_ocorrencia",
        "permite_registrar_ocorrencia",
        "atualizado_por",
        "atualizado_por_nome",
        "atualizado_em",
    }

    DETAIL_EXTRA_FIELDS = {
        "pode_marcar_como_encontrado",
        "pode_resolver_situacao",
        "conciliacao_esta_aberto",
        "ocorrencias",
    }

    def setUp(self):
        super().setUp()
        self.bem_ua1_a = self._criar_bem(
            self.ua1, numero_patrimonial="001.000000001-1"
        )
        self.bem_ua1_b = self._criar_bem(
            self.ua1, numero_patrimonial="001.000000002-2"
        )
        self.bem_ua2 = self._criar_bem(
            self.ua2, numero_patrimonial="001.000000003-3"
        )
        self.bem_fora = self._criar_bem(
            self.ua_fora, numero_patrimonial="001.000000004-4"
        )

        self.item_a = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_ua1,
            bem=self.bem_ua1_a,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
        )
        self.item_b = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_ua1,
            bem=self.bem_ua1_b,
            situacao=constants.DIVERGENTE,
            divergencia="Etiqueta danificada",
            observacao="Divergência",
        )
        OcorrenciaConciliacao.objects.create(
            item=self.item_b,
            situacao=constants.DIVERGENTE,
            divergencia="Etiqueta danificada",
            observacao="Divergência",
            registrado_por=self.gestor_com_ua,
        )
        self.item_ua2 = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_ua2,
            bem=self.bem_ua2,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
        )
        self.item_fora = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_fora,
            bem=self.bem_fora,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
        )

        self.list_url = reverse(
            "itens-conciliacao-list", args=[self.conciliacao_ua1.id]
        )

    def _list_url(self, conciliacao_id):
        return reverse("itens-conciliacao-list", args=[conciliacao_id])

    def _detail_url(self, conciliacao_id, item_id):
        return reverse(
            "itens-conciliacao-detail", args=[conciliacao_id, item_id]
        )

    def _registrar_url(self, conciliacao_id, item_id):
        return reverse(
            "itens-conciliacao-registrar-ocorrencia",
            args=[conciliacao_id, item_id],
        )

    def _excluir_url(self, conciliacao_id, item_id):
        return reverse(
            "itens-conciliacao-excluir-ocorrencia",
            args=[conciliacao_id, item_id],
        )

    def _situacoes_url(self, conciliacao_id, item_id):
        return reverse(
            "itens-conciliacao-situacoes-disponiveis",
            args=[conciliacao_id, item_id],
        )

    def _historico_url(self, conciliacao_id, item_id):
        return reverse(
            "itens-conciliacao-historico",
            args=[conciliacao_id, item_id],
        )

    def test_nao_autenticado_retorna_401(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_operador_ve_apenas_itens_da_sua_ua(self):
        self._auth(self.operador)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.item_a.id, self.item_b.id})

    def test_gestor_sem_ua_ve_itens_da_sua_uo(self):
        self._auth(self.gestor_sem_ua)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.item_a.id, self.item_b.id})

    def test_listagem_outra_conciliacao_mesma_uo(self):
        self._auth(self.gestor_sem_ua)
        response = self.client.get(self._list_url(self.conciliacao_ua2.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.item_ua2.id})

    def test_listagem_conciliacao_fora_do_escopo_retorna_404(self):
        self._auth(self.operador)
        response = self.client.get(self._list_url(self.conciliacao_ua2.id))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_listagem_conciliacao_inexistente_retorna_404(self):
        self._auth(self.gestor_com_ua)
        response = self.client.get(self._list_url(999999))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_filtro_por_situacao(self):
        self._auth(self.operador)
        response = self.client.get(
            self.list_url, {"situacao": constants.DIVERGENTE}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.item_b.id})

    def test_filtro_por_multiplas_situacoes(self):
        bem_nao_encontrado = self._criar_bem(
            self.ua1, numero_patrimonial="001.000000005-5"
        )
        item_nao_encontrado = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_ua1,
            bem=bem_nao_encontrado,
            situacao=constants.NAO_ENCONTRADO,
        )
        self._auth(self.operador)
        response = self.client.get(
            self.list_url,
            {"situacao": f"{constants.DIVERGENTE},{constants.NAO_ENCONTRADO}"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(
            ids, {self.item_b.id, item_nao_encontrado.id}
        )

    def test_filtro_por_situacao_invalida_retorna_400(self):
        self._auth(self.operador)
        response = self.client.get(self.list_url, {"situacao": "invalida"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filtro_por_situacao_com_valor_invalido_na_lista_retorna_400(self):
        self._auth(self.operador)
        response = self.client.get(
            self.list_url,
            {"situacao": f"{constants.DIVERGENTE},invalida"},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filtro_sem_situacao_retorna_itens_sem_filtro(self):
        self._auth(self.operador)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.item_a.id, self.item_b.id})

    def test_filtro_por_tem_ocorrencia_true(self):
        self._auth(self.operador)
        response = self.client.get(self.list_url, {"tem_ocorrencia": "true"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.item_b.id})

    def test_filtro_por_tem_ocorrencia_false(self):
        self._auth(self.operador)
        response = self.client.get(self.list_url, {"tem_ocorrencia": "false"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.item_a.id})

    def test_busca_por_numero_patrimonial(self):
        self._auth(self.operador)
        response = self.client.get(
            self.list_url, {"search": "000000001-1"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.item_a.id})

    def test_listagem_campos_retorna_esperados(self):
        self._auth(self.operador)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data["results"][0].keys()), self.LIST_FIELDS
        )

    def test_listagem_inclui_bem_com_bloqueado_e_localizacao(self):
        self._auth(self.operador)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        bem = response.data["results"][0]["bem"]
        self.assertIn("bloqueado_conciliacao", bem)
        self.assertIn("localizacao", bem)
        self.assertFalse(bem["bloqueado_conciliacao"])

    def test_retrieve_retorna_detalhe_completo(self):
        self._auth(self.operador)
        response = self.client.get(
            self._detail_url(self.conciliacao_ua1.id, self.item_b.id)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.item_b.id)
        self.assertTrue(
            self.DETAIL_EXTRA_FIELDS.issubset(set(response.data.keys()))
        )
        self.assertEqual(len(response.data["ocorrencias"]), 1)
        self.assertTrue(response.data["tem_ocorrencia"])
        self.assertTrue(response.data["conciliacao_esta_aberto"])

    def test_retrieve_fora_do_escopo_retorna_404(self):
        self._auth(self.operador)
        response = self.client.get(
            self._detail_url(self.conciliacao_ua2.id, self.item_ua2.id)
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_item_nao_pertence_a_conciliacao_retorna_404(self):
        self._auth(self.operador)
        response = self.client.get(
            self._detail_url(self.conciliacao_ua1.id, self.item_ua2.id)
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_post_put_delete_nao_permitidos(self):
        self._auth(self.operador)

        post = self.client.post(self.list_url, {}, format="json")
        self.assertEqual(post.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        url = self._detail_url(self.conciliacao_ua1.id, self.item_a.id)
        put = self.client.put(url, {}, format="json")
        self.assertEqual(put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        delete = self.client.delete(url)
        self.assertEqual(delete.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_registrar_ocorrencia_nao_encontrado(self):
        self._auth(self.operador)
        url = self._registrar_url(
            self.conciliacao_ua1.id, self.item_a.id
        )
        response = self.client.post(
            url,
            {
                "situacao": constants.NAO_ENCONTRADO,
                "observacao": "Não localizado",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.item_a.refresh_from_db()
        self.assertEqual(self.item_a.situacao, constants.NAO_ENCONTRADO)
        self.assertTrue(self.item_a.tem_ocorrencia)

    def test_registrar_ocorrencia_divergente_sem_divergencia_retorna_400(self):
        self._auth(self.operador)
        url = self._registrar_url(
            self.conciliacao_ua1.id, self.item_a.id
        )
        response = self.client.post(
            url,
            {"situacao": constants.DIVERGENTE, "divergencia": ""},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("divergencia", response.data)

    def test_registrar_ocorrencia_em_baixa_fisica_retorna_400(self):
        ItemConciliacao.objects.filter(pk=self.item_a.pk).update(
            situacao=constants.BAIXA_FISICA
        )
        self.item_a.refresh_from_db()
        self._auth(self.operador)
        url = self._registrar_url(
            self.conciliacao_ua1.id, self.item_a.id
        )
        response = self.client.post(
            url, {"situacao": constants.NAO_ENCONTRADO}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registrar_ocorrencia_baixa_fisica_rejeitado(self):
        self._auth(self.operador)
        url = self._registrar_url(
            self.conciliacao_ua1.id, self.item_a.id
        )
        response = self.client.post(
            url, {"situacao": constants.BAIXA_FISICA}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registrar_ocorrencia_conciliacao_fechada_retorna_400(self):
        from inventario.models import ConciliacaoUA
        ConciliacaoUA.objects.filter(pk=self.conciliacao_ua1.pk).update(
            status=constants.CONCILIACAO_FECHADO
        )
        self._auth(self.operador)
        url = self._registrar_url(
            self.conciliacao_ua1.id, self.item_a.id
        )
        response = self.client.post(
            url, {"situacao": constants.NAO_ENCONTRADO}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registrar_ocorrencia_edita_ocorrencia_existente(self):
        self._auth(self.operador)
        url = self._registrar_url(
            self.conciliacao_ua1.id, self.item_b.id
        )
        response = self.client.post(
            url,
            {
                "situacao": constants.NAO_ENCONTRADO,
                "observacao": "Agora não foi encontrado",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.item_b.refresh_from_db()
        self.assertEqual(self.item_b.situacao, constants.NAO_ENCONTRADO)
        self.assertEqual(self.item_b.ocorrencias.count(), 1)

    def test_registrar_ocorrencia_fora_do_escopo_retorna_404(self):
        self._auth(self.operador)
        url = self._registrar_url(
            self.conciliacao_ua2.id, self.item_ua2.id
        )
        response = self.client.post(
            url, {"situacao": constants.NAO_ENCONTRADO}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_excluir_ocorrencia(self):
        self._auth(self.operador)
        url = self._excluir_url(
            self.conciliacao_ua1.id, self.item_b.id
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.item_b.refresh_from_db()
        self.assertEqual(self.item_b.ocorrencias.count(), 0)
        self.assertFalse(self.item_b.tem_ocorrencia)

    def test_excluir_ocorrencia_sem_ocorrencia_retorna_400(self):
        self._auth(self.operador)
        url = self._excluir_url(
            self.conciliacao_ua1.id, self.item_a.id
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_excluir_ocorrencia_conciliacao_fechada_retorna_400(self):
        from inventario.models import ConciliacaoUA
        ConciliacaoUA.objects.filter(pk=self.conciliacao_ua1.pk).update(
            status=constants.CONCILIACAO_FECHADO
        )
        self._auth(self.operador)
        url = self._excluir_url(
            self.conciliacao_ua1.id, self.item_b.id
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_excluir_ocorrencia_fora_do_escopo_retorna_404(self):
        self._auth(self.operador)
        url = self._excluir_url(
            self.conciliacao_ua2.id, self.item_ua2.id
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_situacoes_disponiveis_item_sem_ocorrencia(self):
        self._auth(self.operador)
        url = self._situacoes_url(
            self.conciliacao_ua1.id, self.item_a.id
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        values = {s["value"] for s in response.data}
        self.assertNotIn(constants.BAIXA_FISICA, values)
        self.assertNotIn(constants.ENCONTRADO_SEM_DIVERGENCIA, values)
        self.assertIn(constants.DIVERGENTE, values)
        self.assertIn(constants.NAO_ENCONTRADO, values)

    def test_situacoes_disponiveis_item_nao_encontrado(self):
        ItemConciliacao.objects.filter(pk=self.item_a.pk).update(
            situacao=constants.NAO_ENCONTRADO
        )
        self.item_a.refresh_from_db()
        self._auth(self.operador)
        url = self._situacoes_url(
            self.conciliacao_ua1.id, self.item_a.id
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        values = {s["value"] for s in response.data}
        self.assertIn(constants.ENCONTRADO, values)

    def test_historico_do_item_apos_registrar_ocorrencia(self):
        self._auth(self.operador)
        url_registrar = self._registrar_url(
            self.conciliacao_ua1.id, self.item_a.id
        )
        self.client.post(
            url_registrar,
            {"situacao": constants.NAO_ENCONTRADO, "observacao": "Perdido"},
            format="json",
        )

        url_historico = self._historico_url(
            self.conciliacao_ua1.id, self.item_a.id
        )
        response = self.client.get(url_historico)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
        campos = {
            acao["campo"]
            for grupo in response.data
            for acao in grupo["acoes"]
        }
        self.assertIn("situacao", campos)

    def test_historico_item_vazio(self):
        self._auth(self.operador)
        url = self._historico_url(
            self.conciliacao_ua1.id, self.item_a.id
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_operador_fora_da_uo_lista_propria_conciliacao(self):
        self._auth(self.operador_fora)
        response = self.client.get(self._list_url(self.conciliacao_fora.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {self.item_fora.id})
