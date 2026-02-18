from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from bem_patrimonial.models import BemPatrimonial, BaixaFisicaBemPatrimonial, BaixaFisicaBensItem
from bem_patrimonial import constants as bem_constants
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from django.contrib.auth.models import Group
from usuario.constants import GRUPO_GESTOR_PATRIMONIO

from inventario.models import ConciliacaoUA, ItemConciliacao, OcorrenciaConciliacao
from inventario import constants
from inventario.utils_conciliacao.conciliacao_utils import (
    _get_ano_referencia_conciliacao,
    get_or_create_conciliacao,
    _confirmar_baixas_fisicas_pos_conciliacao,
    finalizar_conciliacao,
    get_filtro_bens_baixados,
    criar_itens_conciliacao,
)


class TestGetAnoReferenciaConciliacao(TestCase):
    def test_eventual_com_periodo_final(self):
        conciliacao = MagicMock()
        conciliacao.tipo = constants.CONCILIACAO_EVENTUAL
        conciliacao.periodo_final = date(2025, 6, 15)
        self.assertEqual(_get_ano_referencia_conciliacao(conciliacao), 2025)

    def test_eventual_sem_periodo_final(self):
        conciliacao = MagicMock()
        conciliacao.tipo = constants.CONCILIACAO_EVENTUAL
        conciliacao.periodo_final = None
        with patch("inventario.utils_conciliacao.conciliacao_utils.timezone") as mock_tz:
            mock_tz.localdate.return_value = date(2026, 1, 1)
            self.assertEqual(_get_ano_referencia_conciliacao(conciliacao), 2026)

    def test_anual_chama_get_ano_referencia(self):
        conciliacao = MagicMock()
        conciliacao.tipo = constants.CONCILIACAO_ANUAL
        conciliacao._get_ano_referencia.return_value = 2024
        self.assertEqual(_get_ano_referencia_conciliacao(conciliacao), 2024)


class TestGetOrCreateConciliacao(TestCase):
    def setUp(self):
        self.uo = criar_uo()
        self.ua = criar_ua(uo=self.uo)
        self.usuario = Usuario.objects.create_user(
            username="u", password="x", unidade_administrativa=self.ua, unidade_orcamentaria=self.uo
        )

    @patch("inventario.utils_conciliacao.conciliacao_utils.ConciliacaoUA.objects.get_or_create")
    @patch("inventario.utils_conciliacao.conciliacao_utils.criar_itens_conciliacao")
    def test_created_true_chama_criar_itens(self, mock_criar, mock_get_or_create):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        mock_get_or_create.return_value = (conciliacao, True)
        c, created = get_or_create_conciliacao(self.ua, self.usuario)
        self.assertTrue(created)
        mock_criar.assert_called_once_with(conciliacao)

    @patch("inventario.utils_conciliacao.conciliacao_utils.ConciliacaoUA.objects.get_or_create")
    @patch("inventario.utils_conciliacao.conciliacao_utils.criar_itens_conciliacao")
    def test_created_false_nao_chama_criar_itens(self, mock_criar, mock_get_or_create):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        mock_get_or_create.return_value = (conciliacao, False)
        c, created = get_or_create_conciliacao(self.ua, self.usuario)
        self.assertFalse(created)
        mock_criar.assert_not_called()


class TestGetFiltroBensBaixados(TestCase):
    def test_retorna_q_com_ano_minimo(self):
        q = get_filtro_bens_baixados(2023)
        self.assertIsNotNone(q)


class ConciliacaoUtilsTestBase(TestCase):
    def setUp(self):
        self.uo = criar_uo()
        self.ua = criar_ua(uo=self.uo)
        grupo, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.usuario = Usuario.objects.create_user(
            username="u", password="x", unidade_administrativa=self.ua, unidade_orcamentaria=self.uo
        )
        self.usuario.groups.add(grupo)

    def criar_bem(self, **kwargs):
        defaults = dict(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)


class TestConfirmarBaixasFisicasPosConciliacao(ConciliacaoUtilsTestBase):
    def test_sem_itens_retorna_zero(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_FECHADO,
            criado_por=self.usuario,
        )
        self.assertEqual(_confirmar_baixas_fisicas_pos_conciliacao(conciliacao, self.usuario), 0)

    def test_com_itens_sem_baixa_aceita_retorna_zero(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_FECHADO,
            criado_por=self.usuario,
        )
        bem = self.criar_bem()
        ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
            atualizado_por=self.usuario,
        )
        self.assertEqual(_confirmar_baixas_fisicas_pos_conciliacao(conciliacao, self.usuario), 0)

    def test_com_itens_e_baixa_aceita_atualiza_para_baixa_fisica(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_FECHADO,
            criado_por=self.usuario,
        )
        bem = self.criar_bem()
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
            atualizado_por=self.usuario,
        )
        baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua,
            numero_processo_baixa="2025/001",
            status=bem_constants.ACEITA,
            criado_por=self.usuario,
            data_baixa=timezone.localdate(),
        )
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=bem)
        ano_ref = _get_ano_referencia_conciliacao(conciliacao)
        n = _confirmar_baixas_fisicas_pos_conciliacao(conciliacao, self.usuario)
        self.assertEqual(n, 1)
        item.refresh_from_db()
        self.assertEqual(item.situacao, constants.BAIXA_FISICA)
        self.assertEqual(OcorrenciaConciliacao.objects.filter(item=item).count(), 1)


class TestFinalizarConciliacao(ConciliacaoUtilsTestBase):
    @patch("inventario.utils_conciliacao.conciliacao_utils._confirmar_baixas_fisicas_pos_conciliacao")
    def test_chama_finalizar_e_confirmar(self, mock_confirmar):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        mock_confirmar.return_value = 0
        finalizar_conciliacao(conciliacao, self.usuario)
        conciliacao.refresh_from_db()
        self.assertEqual(conciliacao.status, constants.CONCILIACAO_FECHADO)
        mock_confirmar.assert_called_once_with(conciliacao, self.usuario)


class TestCriarItensConciliacao(ConciliacaoUtilsTestBase):
    def test_eventual_sem_periodo_final_levanta_value_error(self):
        conciliacao = MagicMock()
        conciliacao.tipo = constants.CONCILIACAO_EVENTUAL
        conciliacao.periodo_final = None
        with self.assertRaises(ValueError) as ctx:
            criar_itens_conciliacao(conciliacao)
        self.assertIn("periodo_final", str(ctx.exception))

    def test_eventual_com_periodo_final_cria_itens(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        self.criar_bem()
        criar_itens_conciliacao(conciliacao)
        self.assertEqual(ItemConciliacao.objects.filter(conciliacao=conciliacao).count(), 1)

    def test_anual_cria_itens(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_ANUAL,
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        self.criar_bem()
        criar_itens_conciliacao(conciliacao)
        self.assertEqual(ItemConciliacao.objects.filter(conciliacao=conciliacao).count(), 1)

    def test_herda_situacao_problematica_e_divergente(self):
        conciliacao_antiga = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate() - timedelta(days=400),
            status=constants.CONCILIACAO_FECHADO,
            criado_por=self.usuario,
        )
        bem = self.criar_bem()
        item_antigo = ItemConciliacao.objects.create(
            conciliacao=conciliacao_antiga,
            bem=bem,
            situacao=constants.DIVERGENTE,
            divergencia="Div antiga",
            observacao="Obs antiga",
            atualizado_por=self.usuario,
        )
        OcorrenciaConciliacao.objects.create(
            item=item_antigo,
            situacao=constants.DIVERGENTE,
            divergencia="Div antiga",
            observacao="Obs antiga",
            registrado_por=self.usuario,
        )
        conciliacao_nova = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        criar_itens_conciliacao(conciliacao_nova)
        item_novo = ItemConciliacao.objects.get(conciliacao=conciliacao_nova, bem=bem)
        self.assertEqual(item_novo.situacao, constants.DIVERGENTE)
        self.assertEqual(item_novo.divergencia, "Div antiga")
        self.assertEqual(item_novo.observacao, "Obs antiga")

    def test_herda_nao_encontrado(self):
        conciliacao_antiga = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate() - timedelta(days=400),
            status=constants.CONCILIACAO_FECHADO,
            criado_por=self.usuario,
        )
        bem = self.criar_bem()
        item_antigo = ItemConciliacao.objects.create(
            conciliacao=conciliacao_antiga,
            bem=bem,
            situacao=constants.NAO_ENCONTRADO,
            observacao="Não achado",
            atualizado_por=self.usuario,
        )
        OcorrenciaConciliacao.objects.create(
            item=item_antigo,
            situacao=constants.NAO_ENCONTRADO,
            observacao="Não achado",
            registrado_por=self.usuario,
        )
        conciliacao_nova = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        criar_itens_conciliacao(conciliacao_nova)
        item_novo = ItemConciliacao.objects.get(conciliacao=conciliacao_nova, bem=bem)
        self.assertEqual(item_novo.situacao, constants.NAO_ENCONTRADO)
        self.assertEqual(item_novo.observacao, "Não achado")

    def test_sem_ocorrencia_anterior_inicia_encontrado_sem_divergencia(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        self.criar_bem()
        criar_itens_conciliacao(conciliacao)
        item = ItemConciliacao.objects.get(conciliacao=conciliacao)
        self.assertEqual(item.situacao, constants.ENCONTRADO_SEM_DIVERGENCIA)
        self.assertEqual(item.divergencia, "")
        self.assertEqual(item.observacao, "")
