# Testes para inventario/services/conciliacao_sync.py

import datetime

from django.test import TestCase

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants as bem_constants
from dados_comuns.context import audit_as
from dados_comuns.tests.factories import criar_ua
from usuario.models import Usuario

from inventario.models import ConciliacaoUA, ItemConciliacao, OcorrenciaConciliacao
from inventario import constants as inv_constants
from inventario.services import conciliacao_sync


class ConciliacaoSyncTest(TestCase):
    """Testes para conciliacao_sync: cobre todas as linhas do módulo."""

    @classmethod
    def setUpTestData(cls):
        cls.ua = criar_ua(codigo="001.0001", sigla="UA", nome="Unidade Teste")
        cls.usuario = Usuario.objects.create_user(
            username="gestor",
            password="123",
            unidade_administrativa=cls.ua,
        )

    def _criar_bem(self, status=bem_constants.APROVADO, ua=None):
        ua = ua or self.ua
        return BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-0",
            nome="Bem",
            valor_unitario=100,
            status=status,
            unidade_administrativa=ua,
            criado_por=self.usuario,
        )

    def _criar_conciliacao_aberta(self, ua=None):
        ua = ua or self.ua
        return ConciliacaoUA.objects.create(
            tipo=inv_constants.CONCILIACAO_EVENTUAL,
            periodo_final=datetime.date.today(),
            unidade_administrativa=ua,
            criado_por=self.usuario,
            status=inv_constants.CONCILIACAO_EM_ABERTO,
        )

    # --- remover_bem_de_conciliacoes_em_aberto (cobre _conciliacoes_em_aberto com ua_id) ---

    def test_remover_bem_ua_id_none_retorna_cedo(self):
        bem = self._criar_bem()
        conciliacao_sync.remover_bem_de_conciliacoes_em_aberto(bem.pk, None)
        # não levanta e não altera nada
        self.assertEqual(ItemConciliacao.objects.count(), 0)

    def test_remover_bem_remove_itens_das_conciliacoes_em_aberto(self):
        conciliacao = self._criar_conciliacao_aberta()
        bem = self._criar_bem()
        ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=inv_constants.ENCONTRADO_SEM_DIVERGENCIA,
        )
        self.assertEqual(ItemConciliacao.objects.count(), 1)
        conciliacao_sync.remover_bem_de_conciliacoes_em_aberto(bem.pk, self.ua.pk)
        self.assertEqual(ItemConciliacao.objects.count(), 0)

    # --- incluir_ou_atualizar_bem_em_conciliacoes_em_aberto ---

    def test_incluir_ou_atualizar_ua_id_none_retorna_cedo(self):
        bem = self._criar_bem()
        with audit_as(self.usuario):
            conciliacao_sync.incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(
                bem, None
            )
        self.assertEqual(ItemConciliacao.objects.count(), 0)

    def test_incluir_bem_novo_em_conciliacao_cria_item(self):
        conciliacao = self._criar_conciliacao_aberta()
        bem = self._criar_bem()
        with audit_as(self.usuario):
            conciliacao_sync.incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(
                bem, self.ua.pk
            )
        item = ItemConciliacao.objects.get(conciliacao=conciliacao, bem=bem)
        self.assertEqual(item.situacao, inv_constants.ENCONTRADO_SEM_DIVERGENCIA)
        self.assertEqual(item.atualizado_por, self.usuario)
        bem.refresh_from_db()
        self.assertFalse(bem.bloqueado_conciliacao)

    def test_incluir_bem_pendente_acao_nao_deleta_ocorrencias_atualiza_item(self):
        """Cobre ramo pendente -> continue (não entra no if not em_processo)."""
        conciliacao = self._criar_conciliacao_aberta()
        bem = self._criar_bem(status=bem_constants.BLOQUEADO)
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=inv_constants.NAO_ENCONTRADO,
        )
        OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=inv_constants.DIVERGENTE,
            registrado_por=self.usuario,
        )
        with audit_as(self.usuario):
            conciliacao_sync.incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(
                bem, self.ua.pk
            )
        self.assertEqual(OcorrenciaConciliacao.objects.filter(item=item).count(), 1)
        item.refresh_from_db()
        # Quando pendente=True o código faz continue e não atualiza o item
        self.assertEqual(item.situacao, inv_constants.NAO_ENCONTRADO)

    def test_incluir_bem_em_processo_baixa_nao_deleta_ocorrencias_marca_bloqueado(self):
        """Cobre ramo em_processo=True: não deleta ocorrências EM_PROCESSO_BAIXA_FISICA."""
        conciliacao = self._criar_conciliacao_aberta()
        bem = self._criar_bem()
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=inv_constants.EM_PROCESSO_BAIXA_FISICA,
        )
        OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=inv_constants.EM_PROCESSO_BAIXA_FISICA,
            registrado_por=self.usuario,
        )
        with audit_as(self.usuario):
            conciliacao_sync.incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(
                bem, self.ua.pk
            )
        self.assertEqual(OcorrenciaConciliacao.objects.filter(item=item).count(), 1)
        bem.refresh_from_db()
        self.assertTrue(bem.bloqueado_conciliacao)

    def test_incluir_bem_sem_em_processo_deleta_outras_ocorrencias_atualiza_item(self):
        """Cobre ramo not em_processo: delete ocorrências (exceto EM_PROCESSO_BAIXA_FISICA)."""
        conciliacao = self._criar_conciliacao_aberta()
        bem = self._criar_bem()
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=inv_constants.DIVERGENTE,
        )
        OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=inv_constants.DIVERGENTE,
            registrado_por=self.usuario,
        )
        with audit_as(self.usuario):
            conciliacao_sync.incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(
                bem, self.ua.pk
            )
        self.assertEqual(OcorrenciaConciliacao.objects.filter(item=item).count(), 0)
        item.refresh_from_db()
        self.assertEqual(item.situacao, inv_constants.ENCONTRADO_SEM_DIVERGENCIA)
        bem.refresh_from_db()
        self.assertFalse(bem.bloqueado_conciliacao)

    # --- sync_bem_pos_save ---

    def test_sync_bem_excluido_remove_da_conciliacao_e_retorna(self):
        conciliacao = self._criar_conciliacao_aberta()
        bem = self._criar_bem()
        ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=inv_constants.ENCONTRADO_SEM_DIVERGENCIA,
        )
        bem.excluido = True
        conciliacao_sync.sync_bem_pos_save(bem)
        self.assertEqual(ItemConciliacao.objects.count(), 0)

    def test_sync_bem_mudou_ua_remove_da_antiga_e_inclui_na_nova_se_houver_conciliacao(self):
        ua2 = criar_ua(uo=self.ua.unidade_orcamentaria, codigo="001.0002", sigla="UA2", nome="Unidade 2")
        conciliacao_antiga = self._criar_conciliacao_aberta()
        bem = self._criar_bem(ua=self.ua)
        ItemConciliacao.objects.create(
            conciliacao=conciliacao_antiga,
            bem=bem,
            situacao=inv_constants.ENCONTRADO_SEM_DIVERGENCIA,
        )
        conciliacao_nova = self._criar_conciliacao_aberta(ua=ua2)
        bem.unidade_administrativa = ua2
        bem.unidade_administrativa_id = ua2.pk
        with audit_as(self.usuario):
            conciliacao_sync.sync_bem_pos_save(bem, old_ua_id=self.ua.pk)
        self.assertEqual(
            ItemConciliacao.objects.filter(conciliacao=conciliacao_antiga).count(), 0
        )
        self.assertEqual(
            ItemConciliacao.objects.filter(conciliacao=conciliacao_nova, bem=bem).count(),
            1,
        )

    def test_sync_bem_mudou_ua_sem_conciliacao_na_nova_apenas_remove(self):
        ua2 = criar_ua(uo=self.ua.unidade_orcamentaria, codigo="001.0003", sigla="UA3", nome="Unidade 3")
        conciliacao_antiga = self._criar_conciliacao_aberta()
        bem = self._criar_bem(ua=self.ua)
        ItemConciliacao.objects.create(
            conciliacao=conciliacao_antiga,
            bem=bem,
            situacao=inv_constants.ENCONTRADO_SEM_DIVERGENCIA,
        )
        bem.unidade_administrativa = ua2
        bem.unidade_administrativa_id = ua2.pk
        conciliacao_sync.sync_bem_pos_save(bem, old_ua_id=self.ua.pk)
        self.assertEqual(
            ItemConciliacao.objects.filter(conciliacao=conciliacao_antiga).count(), 0
        )
        self.assertEqual(ItemConciliacao.objects.filter(bem=bem).count(), 0)

    def test_sync_bem_mesma_ua_com_conciliacao_inclui_ou_atualiza(self):
        conciliacao = self._criar_conciliacao_aberta()
        bem = self._criar_bem()
        with audit_as(self.usuario):
            conciliacao_sync.sync_bem_pos_save(bem)
        self.assertEqual(
            ItemConciliacao.objects.filter(conciliacao=conciliacao, bem=bem).count(), 1
        )

    def test_sync_bem_mesma_ua_sem_conciliacao_nao_faz_nada(self):
        bem = self._criar_bem()
        with audit_as(self.usuario):
            conciliacao_sync.sync_bem_pos_save(bem)
        self.assertEqual(ItemConciliacao.objects.count(), 0)

    # --- Cobertura de funções internas (linhas que só são atingidas por elas) ---

    def test_conciliacoes_em_aberto_retorna_none_quando_ua_id_vazio(self):
        qs = conciliacao_sync._conciliacoes_em_aberto(None)
        self.assertEqual(list(qs), [])
        self.assertEqual(conciliacao_sync._conciliacoes_em_aberto(0).count(), 0)

    def test_status_pendente_acao_true_para_aguardando_aprovacao(self):
        bem = self._criar_bem(status=bem_constants.AGUARDANDO_APROVACAO)
        self.assertTrue(conciliacao_sync._status_pendente_acao(bem))

    def test_status_pendente_acao_true_para_baixa_fisica_aguardando(self):
        bem = self._criar_bem(status=bem_constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)
        self.assertTrue(conciliacao_sync._status_pendente_acao(bem))

    def test_status_pendente_acao_false_para_aprovado(self):
        bem = self._criar_bem(status=bem_constants.APROVADO)
        self.assertFalse(conciliacao_sync._status_pendente_acao(bem))

    def test_tem_em_processo_baixa_retorna_false_quando_ua_id_none(self):
        bem = self._criar_bem()
        self.assertFalse(conciliacao_sync._tem_em_processo_baixa(bem.pk, None))

    def test_tem_em_processo_baixa_retorna_false_sem_ocorrencia(self):
        bem = self._criar_bem()
        self.assertFalse(
            conciliacao_sync._tem_em_processo_baixa(bem.pk, self.ua.pk)
        )