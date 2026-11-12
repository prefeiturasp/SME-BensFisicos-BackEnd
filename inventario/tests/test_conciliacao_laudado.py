from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework import status

from bem_patrimonial import constants as bem_constants
from dados_comuns.historico_consulta import limpar_justificativa_historico
from dados_comuns.models import HistoricoGeral
from inventario import constants
from inventario.models import ConciliacaoUA, ItemConciliacao
from inventario.services import conciliacao_sync
from inventario.tests.conciliacao_base import ConciliacaoAPIBaseTestCase
from inventario.utils_conciliacao.conciliacao_utils import criar_itens_conciliacao


class ConciliacaoLaudadoTestCase(ConciliacaoAPIBaseTestCase):
    username_prefix = "laudado_"

    def _criar_bem_laudado(self, ua, **kwargs):
        kwargs.setdefault("status", bem_constants.LAUDADO_PARA_BAIXA)
        return self._criar_bem(ua, **kwargs)

    def test_criar_itens_laudado_vira_em_processo_e_normal_permanece_encontrado(self):
        bem_laudado = self._criar_bem_laudado(self.ua1, numero_patrimonial="001.000000010-1")
        bem_normal = self._criar_bem(self.ua1, numero_patrimonial="001.000000011-1")
        criar_itens_conciliacao(self.conciliacao_ua1)

        item_laudado = ItemConciliacao.objects.get(conciliacao=self.conciliacao_ua1, bem=bem_laudado)
        item_normal = ItemConciliacao.objects.get(conciliacao=self.conciliacao_ua1, bem=bem_normal)

        self.assertEqual(item_laudado.situacao, constants.EM_PROCESSO_BAIXA_FISICA)
        self.assertEqual(item_normal.situacao, constants.ENCONTRADO_SEM_DIVERGENCIA)

        bem_laudado.refresh_from_db()
        self.assertEqual(bem_laudado.status, bem_constants.LAUDADO_PARA_BAIXA)

    def test_api_list_laudado_distinto_de_processo_comum(self):
        bem_laudado = self._criar_bem_laudado(self.ua1, numero_patrimonial="001.000000020-1")
        bem_comum = self._criar_bem(self.ua1, numero_patrimonial="001.000000021-1")
        item_laudado = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_ua1,
            bem=bem_laudado,
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
        )
        ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_ua1,
            bem=bem_comum,
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
        )

        self._auth(self.operador)
        url = reverse("itens-conciliacao-list", args=[self.conciliacao_ua1.id])
        response = self.client.get(url, {"bem_status": bem_constants.LAUDADO_PARA_BAIXA})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {row["id"] for row in response.data["results"]}
        self.assertEqual(ids, {item_laudado.id})

        row = response.data["results"][0]
        self.assertEqual(row["bem"]["status"], bem_constants.LAUDADO_PARA_BAIXA)
        self.assertIn("status_display", row["bem"])
        self.assertEqual(row["bem"]["status_display"], "Laudado para Baixa")
        self.assertEqual(row["situacao"], constants.EM_PROCESSO_BAIXA_FISICA)

        # Sem filtro: ambos aparecem, mas com bem.status distinto.
        response_all = self.client.get(url)
        self.assertEqual(response_all.status_code, status.HTTP_200_OK)
        por_id = {row["id"]: row for row in response_all.data["results"]}
        self.assertEqual(por_id[item_laudado.id]["bem"]["status"], bem_constants.LAUDADO_PARA_BAIXA)

    def test_filtro_bem_status_invalido_retorna_400(self):
        self._auth(self.operador)
        url = reverse("itens-conciliacao-list", args=[self.conciliacao_ua1.id])
        response = self.client.get(url, {"bem_status": "invalido"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("bem_status", response.data)

    def test_filtro_situacao_laudado_retorna_apenas_em_processo_laudado(self):
        bem_laudado_processo = self._criar_bem_laudado(self.ua1, numero_patrimonial="001.000000022-1")
        bem_laudado_encontrado = self._criar_bem_laudado(self.ua1, numero_patrimonial="001.000000023-1")
        bem_comum_divergente = self._criar_bem(self.ua1, numero_patrimonial="001.000000024-1")
        item_processo = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_ua1,
            bem=bem_laudado_processo,
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
        )
        ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_ua1,
            bem=bem_laudado_encontrado,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
        )
        item_divergente = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_ua1,
            bem=bem_comum_divergente,
            situacao=constants.DIVERGENTE,
            divergencia="x",
        )

        self._auth(self.operador)
        url = reverse("itens-conciliacao-list", args=[self.conciliacao_ua1.id])

        response = self.client.get(url, {"situacao": bem_constants.LAUDADO_PARA_BAIXA})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({row["id"] for row in response.data["results"]}, {item_processo.id})

        response_or = self.client.get(url, {"situacao": f"{constants.DIVERGENTE},{bem_constants.LAUDADO_PARA_BAIXA}"})
        self.assertEqual(response_or.status_code, status.HTTP_200_OK)
        self.assertEqual({row["id"] for row in response_or.data["results"]}, {item_divergente.id, item_processo.id})

    def test_finalizar_nao_confirma_laudado_como_baixa(self):
        from django.utils import timezone

        from bem_patrimonial.models import BaixaFisicaBemPatrimonial, BaixaFisicaBensItem

        bem = self._criar_bem_laudado(self.ua1, numero_patrimonial="001.000000025-1")
        item = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_ua1,
            bem=bem,
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
        )
        baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua1,
            status=bem_constants.ACEITA,
            criado_por=self.gestor_com_ua,
            data_baixa=timezone.localdate(),
        )
        BaixaFisicaBensItem.objects.create(bem=bem, baixa=baixa)

        self._auth(self.gestor_com_ua)
        url = reverse("conciliacoes-finalizar", args=[self.conciliacao_ua1.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.situacao, constants.EM_PROCESSO_BAIXA_FISICA)

    def test_sync_laudado_marca_em_processo_sem_bloqueio(self):
        from dados_comuns.context import audit_as

        conciliacao = self.conciliacao_ua1
        bem = self._criar_bem_laudado(self.ua1, numero_patrimonial="001.000000030-1")
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
        )
        with audit_as(self.gestor_com_ua):
            conciliacao_sync.incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(bem, self.ua1.pk)

        item.refresh_from_db()
        bem.refresh_from_db()
        self.assertEqual(item.situacao, constants.EM_PROCESSO_BAIXA_FISICA)
        self.assertFalse(bem.bloqueado_conciliacao)
        self.assertEqual(bem.status, bem_constants.LAUDADO_PARA_BAIXA)

    def test_registrar_laudado_bloqueia_outra_situacao(self):
        bem = self._criar_bem_laudado(self.ua1, numero_patrimonial="001.000000031-1")
        item = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_ua1,
            bem=bem,
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
        )
        self._auth(self.operador)
        url = reverse("itens-conciliacao-registrar-ocorrencia", args=[self.conciliacao_ua1.id, item.id])
        response = self.client.post(url, {"situacao": constants.NAO_ENCONTRADO}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_excluir_laudado_volta_para_em_processo(self):
        from inventario.models import OcorrenciaConciliacao

        bem = self._criar_bem_laudado(self.ua1, numero_patrimonial="001.000000032-1")
        item = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_ua1,
            bem=bem,
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
        )
        OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
            registrado_por=self.gestor_com_ua,
        )
        self._auth(self.operador)
        url = reverse("itens-conciliacao-excluir-ocorrencia", args=[self.conciliacao_ua1.id, item.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.situacao, constants.EM_PROCESSO_BAIXA_FISICA)
        self.assertEqual(item.observacao, "")
        self.assertEqual(item.divergencia, "")

    def test_situacoes_disponiveis_laudado_so_em_processo(self):
        bem = self._criar_bem_laudado(self.ua1, numero_patrimonial="001.000000033-1")
        item = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_ua1,
            bem=bem,
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
        )
        self._auth(self.operador)
        url = reverse("itens-conciliacao-situacoes-disponiveis", args=[self.conciliacao_ua1.id, item.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row["value"] for row in response.data], [constants.EM_PROCESSO_BAIXA_FISICA])

    def test_historico_sem_sufixo_via_api_e_limpeza_legado(self):
        self._auth(self.gestor_com_ua)
        # Cria item para registrar ocorrência.
        bem = self._criar_bem(self.ua1, numero_patrimonial="001.000000040-1")
        item = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao_ua1,
            bem=bem,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
        )

        url_registrar = reverse(
            "itens-conciliacao-registrar-ocorrencia",
            args=[self.conciliacao_ua1.id, item.id],
        )
        resp = self.client.post(url_registrar, {"situacao": constants.NAO_ENCONTRADO, "observacao": "x"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        url_finalizar = reverse("conciliacoes-finalizar", args=[self.conciliacao_ua1.id])
        resp_fin = self.client.post(url_finalizar)
        self.assertEqual(resp_fin.status_code, status.HTTP_200_OK)

        for model, pk in [
            (ConciliacaoUA, self.conciliacao_ua1.pk),
            (ItemConciliacao, item.pk),
        ]:
            ct = ContentType.objects.get_for_model(model)
            justificativas = list(
                HistoricoGeral.objects.filter(content_type=ct, object_id=str(pk)).values_list(
                    "justificativa", flat=True
                )
            )
            self.assertTrue(justificativas)
            for texto in justificativas:
                self.assertNotIn("via API", texto)

        # Limpeza de legado na leitura.
        self.assertEqual(limpar_justificativa_historico("Conciliação criada via API"), "Conciliação criada")
        self.assertEqual(limpar_justificativa_historico("Ocorrência registrada via API"), "Ocorrência registrada")
        self.assertEqual(
            limpar_justificativa_historico("Movimentação aprovada via Django admin"), "Movimentação aprovada"
        )
        self.assertEqual(limpar_justificativa_historico("Conciliação criada"), "Conciliação criada")
