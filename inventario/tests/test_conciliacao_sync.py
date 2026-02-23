"""Testes para inventario.services.conciliacao_sync."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO

from bem_patrimonial import constants as bem_constants
from bem_patrimonial.models import BemPatrimonial

from inventario.models import ConciliacaoUA, ItemConciliacao, OcorrenciaConciliacao
from inventario import constants
from inventario.services.conciliacao_sync import (
    _conciliacoes_em_aberto,
    _status_pendente_acao,
    _tem_em_processo_baixa,
    remover_bem_de_conciliacoes_em_aberto,
    incluir_ou_atualizar_bem_em_conciliacoes_em_aberto,
    sync_bem_pos_save,
)


User = get_user_model()


class TestConciliacaoSyncBase(TestCase):
    """Base para testes de conciliacao_sync."""

    def setUp(self):
        self.uo = criar_uo()
        self.ua = criar_ua(uo=self.uo, status=UnidadeAdministrativa.ATIVA)
        self.ua_outra = criar_ua(uo=self.uo, status=UnidadeAdministrativa.ATIVA)
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.usuario = User.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            is_staff=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.usuario.groups.add(grupo_gestor)

    def _mk_bem(self, **kwargs):
        defaults = {
            "nome": "Bem Teste",
            "descricao": "Descrição",
            "valor_unitario": 100,
            "marca": "Marca",
            "modelo": "Modelo",
            "numero_processo": "PROC-1",
            "unidade_administrativa": self.ua,
            "criado_por": self.usuario,
            "status": bem_constants.APROVADO,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def _mk_conciliacao(self, **kwargs):
        defaults = {
            "unidade_administrativa": self.ua,
            "tipo": constants.CONCILIACAO_EVENTUAL,
            "periodo_final": timezone.localdate(),
            "status": constants.CONCILIACAO_EM_ABERTO,
            "criado_por": self.usuario,
        }
        defaults.update(kwargs)
        return ConciliacaoUA.objects.create(**defaults)


class TestConciliacoesEmAberto(TestConciliacaoSyncBase):
    """Testes para _conciliacoes_em_aberto()."""

    def test_retorna_none_quando_ua_id_none(self):
        qs = _conciliacoes_em_aberto(None)
        self.assertEqual(qs.count(), 0)

    def test_retorna_apenas_conciliacoes_em_aberto(self):
        from datetime import timedelta
        conc_aberta = self._mk_conciliacao(
            status=constants.CONCILIACAO_EM_ABERTO,
            periodo_final=timezone.localdate(),
        )
        self._mk_conciliacao(
            status=constants.CONCILIACAO_FECHADO,
            periodo_final=timezone.localdate() + timedelta(days=1),
        )
        qs = _conciliacoes_em_aberto(self.ua.pk)
        self.assertEqual(qs.count(), 1)
        self.assertIn(conc_aberta, qs)

    def test_filtra_por_ua_id(self):
        conc_ua1 = self._mk_conciliacao(unidade_administrativa=self.ua)
        self._mk_conciliacao(unidade_administrativa=self.ua_outra)
        qs = _conciliacoes_em_aberto(self.ua.pk)
        self.assertEqual(qs.count(), 1)
        self.assertIn(conc_ua1, qs)


class TestStatusPendenteAcao(TestConciliacaoSyncBase):
    """Testes para _status_pendente_acao()."""

    def test_retorna_true_para_status_bloqueado(self):
        bem = self._mk_bem(status=bem_constants.BLOQUEADO)
        self.assertTrue(_status_pendente_acao(bem))

    def test_retorna_true_para_status_aguardando_aprovacao(self):
        bem = self._mk_bem(status=bem_constants.AGUARDANDO_APROVACAO)
        self.assertTrue(_status_pendente_acao(bem))

    def test_retorna_false_para_status_aprovado(self):
        bem = self._mk_bem(status=bem_constants.APROVADO)
        self.assertFalse(_status_pendente_acao(bem))

    def test_retorna_false_para_status_baixa_fisica(self):
        bem = self._mk_bem(status=bem_constants.BAIXA_FISICA)
        self.assertFalse(_status_pendente_acao(bem))


class TestTemEmProcessoBaixa(TestConciliacaoSyncBase):
    """Testes para _tem_em_processo_baixa()."""

    def test_retorna_false_quando_ua_id_none(self):
        bem = self._mk_bem()
        self.assertFalse(_tem_em_processo_baixa(bem.pk, None))

    def test_retorna_false_quando_nao_tem_ocorrencia(self):
        bem = self._mk_bem()
        self.assertFalse(_tem_em_processo_baixa(bem.pk, self.ua.pk))

    def test_retorna_true_quando_tem_ocorrencia_em_processo(self):
        bem = self._mk_bem()
        conciliacao = self._mk_conciliacao()
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
        )
        OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
            observacao="Teste",
            registrado_por=self.usuario,
        )
        self.assertTrue(_tem_em_processo_baixa(bem.pk, self.ua.pk))

    def test_retorna_false_quando_ocorrencia_nao_em_processo(self):
        bem = self._mk_bem()
        conciliacao = self._mk_conciliacao()
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
        )
        OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=constants.ENCONTRADO,
            observacao="Teste",
            registrado_por=self.usuario,
        )
        self.assertFalse(_tem_em_processo_baixa(bem.pk, self.ua.pk))


class TestRemoverBemDeConciliacoesEmAberto(TestConciliacaoSyncBase):
    """Testes para remover_bem_de_conciliacoes_em_aberto()."""

    def test_nao_faz_nada_quando_ua_id_none(self):
        bem = self._mk_bem()
        conciliacao = self._mk_conciliacao()
        ItemConciliacao.objects.create(
            conciliacao=conciliacao, bem=bem, situacao=constants.ENCONTRADO_SEM_DIVERGENCIA
        )
        remover_bem_de_conciliacoes_em_aberto(bem.pk, None)
        self.assertEqual(ItemConciliacao.objects.filter(bem=bem).count(), 1)

    def test_remove_item_de_conciliacao_em_aberto(self):
        from datetime import timedelta
        bem = self._mk_bem()
        conc_aberta = self._mk_conciliacao(
            status=constants.CONCILIACAO_EM_ABERTO,
            periodo_final=timezone.localdate(),
        )
        conc_fechada = self._mk_conciliacao(
            status=constants.CONCILIACAO_FECHADO,
            periodo_final=timezone.localdate() + timedelta(days=1),
        )
        item_aberta = ItemConciliacao.objects.create(
            conciliacao=conc_aberta, bem=bem, situacao=constants.ENCONTRADO_SEM_DIVERGENCIA
        )
        item_fechada = ItemConciliacao.objects.create(
            conciliacao=conc_fechada, bem=bem, situacao=constants.ENCONTRADO_SEM_DIVERGENCIA
        )
        remover_bem_de_conciliacoes_em_aberto(bem.pk, self.ua.pk)
        self.assertFalse(ItemConciliacao.objects.filter(pk=item_aberta.pk).exists())
        self.assertTrue(ItemConciliacao.objects.filter(pk=item_fechada.pk).exists())


class TestIncluirOuAtualizarBemEmConciliacoesEmAberto(TestConciliacaoSyncBase):
    """Testes para incluir_ou_atualizar_bem_em_conciliacoes_em_aberto()."""

    def test_nao_faz_nada_quando_ua_id_none(self):
        bem = self._mk_bem()
        incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(bem, None)
        self.assertEqual(ItemConciliacao.objects.filter(bem=bem).count(), 0)

    @patch("inventario.services.conciliacao_sync.get_user")
    def test_cria_item_quando_nao_existe(self, mock_get_user):
        mock_get_user.return_value = self.usuario
        bem = self._mk_bem()
        conciliacao = self._mk_conciliacao()
        incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(bem, self.ua.pk)
        item = ItemConciliacao.objects.get(conciliacao=conciliacao, bem=bem)
        self.assertEqual(item.situacao, constants.ENCONTRADO_SEM_DIVERGENCIA)
        self.assertEqual(item.atualizado_por, self.usuario)

    @patch("inventario.services.conciliacao_sync.get_user")
    def test_atualiza_item_existente_quando_nao_pendente(self, mock_get_user):
        mock_get_user.return_value = self.usuario
        bem = self._mk_bem(status=bem_constants.APROVADO)
        conciliacao = self._mk_conciliacao()
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=constants.NAO_ENCONTRADO,
            observacao="Antiga",
            divergencia="Antiga",
        )
        incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(bem, self.ua.pk)
        item.refresh_from_db()
        self.assertEqual(item.situacao, constants.ENCONTRADO_SEM_DIVERGENCIA)
        self.assertEqual(item.observacao, "")
        self.assertEqual(item.divergencia, "")
        self.assertEqual(item.atualizado_por, self.usuario)

    @patch("inventario.services.conciliacao_sync.get_user")
    def test_nao_atualiza_quando_bem_pendente(self, mock_get_user):
        mock_get_user.return_value = self.usuario
        bem = self._mk_bem(status=bem_constants.AGUARDANDO_APROVACAO)
        conciliacao = self._mk_conciliacao()
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=constants.NAO_ENCONTRADO,
            observacao="Antiga",
        )
        incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(bem, self.ua.pk)
        item.refresh_from_db()
        # Não deve atualizar quando bem está pendente
        self.assertEqual(item.situacao, constants.NAO_ENCONTRADO)
        self.assertEqual(item.observacao, "Antiga")

    @patch("inventario.services.conciliacao_sync.get_user")
    def test_marca_bloqueado_conciliacao_quando_em_processo_baixa(self, mock_get_user):
        mock_get_user.return_value = self.usuario
        bem = self._mk_bem()
        conciliacao = self._mk_conciliacao()
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao, bem=bem, situacao=constants.ENCONTRADO_SEM_DIVERGENCIA
        )
        OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
            observacao="Teste",
            registrado_por=self.usuario,
        )
        incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(bem, self.ua.pk)
        bem.refresh_from_db()
        self.assertTrue(bem.bloqueado_conciliacao)

    @patch("inventario.services.conciliacao_sync.get_user")
    def test_remove_ocorrencias_exceto_em_processo_baixa(self, mock_get_user):
        """Quando não há em_processo_baixa, remove ocorrências exceto EM_PROCESSO_BAIXA_FISICA."""
        mock_get_user.return_value = self.usuario
        bem = self._mk_bem()
        conciliacao = self._mk_conciliacao()
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao, bem=bem, situacao=constants.ENCONTRADO_SEM_DIVERGENCIA
        )
        ocorr1 = OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=constants.ENCONTRADO,
            observacao="Ocorrência 1",
            registrado_por=self.usuario,
        )
        # Não criar ocorrência EM_PROCESSO_BAIXA_FISICA para que em_processo seja False
        incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(bem, self.ua.pk)
        # Quando não há em_processo, ocorrências exceto EM_PROCESSO_BAIXA_FISICA são removidas
        self.assertFalse(OcorrenciaConciliacao.objects.filter(pk=ocorr1.pk).exists())

    @patch("inventario.services.conciliacao_sync.get_user")
    def test_nao_remove_ocorrencias_quando_em_processo_baixa(self, mock_get_user):
        """Quando há em_processo_baixa, não remove nenhuma ocorrência."""
        mock_get_user.return_value = self.usuario
        bem = self._mk_bem()
        conciliacao = self._mk_conciliacao()
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao, bem=bem, situacao=constants.ENCONTRADO_SEM_DIVERGENCIA
        )
        ocorr1 = OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=constants.ENCONTRADO,
            observacao="Ocorrência 1",
            registrado_por=self.usuario,
        )
        ocorr2 = OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
            observacao="Ocorrência 2",
            registrado_por=self.usuario,
        )
        incluir_ou_atualizar_bem_em_conciliacoes_em_aberto(bem, self.ua.pk)
        # Quando há em_processo, nenhuma ocorrência é removida
        self.assertTrue(OcorrenciaConciliacao.objects.filter(pk=ocorr1.pk).exists())
        self.assertTrue(OcorrenciaConciliacao.objects.filter(pk=ocorr2.pk).exists())


class TestSyncBemPosSave(TestConciliacaoSyncBase):
    """Testes para sync_bem_pos_save()."""

    @patch("inventario.services.conciliacao_sync.get_user")
    def test_remove_quando_bem_excluido(self, mock_get_user):
        mock_get_user.return_value = self.usuario
        bem = self._mk_bem()
        conciliacao = self._mk_conciliacao()
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao, bem=bem, situacao=constants.ENCONTRADO_SEM_DIVERGENCIA
        )
        bem.excluido = True
        sync_bem_pos_save(bem)
        self.assertFalse(ItemConciliacao.objects.filter(pk=item.pk).exists())

    @patch("inventario.services.conciliacao_sync.get_user")
    def test_remove_de_ua_antiga_e_inclui_em_nova_quando_muda_ua(self, mock_get_user):
        mock_get_user.return_value = self.usuario
        bem = self._mk_bem(unidade_administrativa=self.ua)
        conc_antiga = self._mk_conciliacao(unidade_administrativa=self.ua)
        conc_nova = self._mk_conciliacao(unidade_administrativa=self.ua_outra)
        item_antiga = ItemConciliacao.objects.create(
            conciliacao=conc_antiga, bem=bem, situacao=constants.ENCONTRADO_SEM_DIVERGENCIA
        )
        bem.unidade_administrativa = self.ua_outra
        sync_bem_pos_save(bem, old_ua_id=self.ua.pk)
        self.assertFalse(ItemConciliacao.objects.filter(pk=item_antiga.pk).exists())
        self.assertTrue(
            ItemConciliacao.objects.filter(
                conciliacao=conc_nova, bem=bem
            ).exists()
        )

    @patch("inventario.services.conciliacao_sync.get_user")
    def test_inclui_quando_nao_mudou_ua_e_tem_conciliacao_aberta(self, mock_get_user):
        mock_get_user.return_value = self.usuario
        bem = self._mk_bem(unidade_administrativa=self.ua)
        conciliacao = self._mk_conciliacao()
        sync_bem_pos_save(bem)
        self.assertTrue(
            ItemConciliacao.objects.filter(conciliacao=conciliacao, bem=bem).exists()
        )

    @patch("inventario.services.conciliacao_sync.get_user")
    def test_nao_faz_nada_quando_nao_tem_conciliacao_aberta(self, mock_get_user):
        mock_get_user.return_value = self.usuario
        bem = self._mk_bem()
        self._mk_conciliacao(status=constants.CONCILIACAO_FECHADO)
        sync_bem_pos_save(bem)
        self.assertEqual(ItemConciliacao.objects.filter(bem=bem).count(), 0)
