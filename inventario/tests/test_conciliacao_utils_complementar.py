"""Testes complementares para inventario.utils_conciliacao.conciliacao_utils."""
from datetime import date, timedelta
from unittest.mock import patch

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
    get_filtro_bens_baixados,
    criar_itens_conciliacao,
    _confirmar_baixas_fisicas_pos_conciliacao,
)


class TestGetFiltroBensBaixados(TestCase):
    """Testes complementares para get_filtro_bens_baixados."""

    def test_filtro_retorna_q_correto(self):
        """Filtro retorna Q com condições corretas."""
        q = get_filtro_bens_baixados(2023)
        self.assertIsNotNone(q)
        # Verificar que é um objeto Q
        from django.db.models import Q
        self.assertIsInstance(q, Q)


class TestCriarItensConciliacaoComplementar(TestCase):
    """Testes complementares para criar_itens_conciliacao."""

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
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="P",
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
            localizacao="Local",
        )
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def test_inclui_bens_baixados_ano_anterior(self):
        """Inclui bens baixados no ano anterior ao da conciliação."""
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate().replace(year=2024, month=6, day=15),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        # Criar bem baixado no ano anterior (2023)
        bem_baixado = self.criar_bem(status=bem_constants.BAIXA_FISICA)
        baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua,
            numero_processo_baixa="2023/001",
            status=bem_constants.ACEITA,
            criado_por=self.usuario,
            data_baixa=timezone.localdate().replace(year=2023, month=6, day=15),
        )
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=bem_baixado)
        
        criar_itens_conciliacao(conciliacao)
        # Deve incluir o bem baixado
        self.assertTrue(ItemConciliacao.objects.filter(conciliacao=conciliacao, bem=bem_baixado).exists())

    def test_exclui_bens_baixados_antes_do_ano_anterior(self):
        """Exclui bens baixados antes do ano anterior."""
        # Para conciliação de 2024 (periodo_final=2024), ano_conciliacao = 2023, ano_baixa_minimo = 2022
        # Então apenas bens baixados em 2022 ou depois são incluídos
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate().replace(year=2024, month=6, day=15),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        # Criar bem baixado há mais de um ano antes do mínimo (2021)
        bem_baixado_antigo = self.criar_bem(status=bem_constants.BAIXA_FISICA)
        baixa_antiga = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua,
            numero_processo_baixa="2021/001",
            status=bem_constants.ACEITA,
            criado_por=self.usuario,
            data_baixa=timezone.localdate().replace(year=2021, month=6, day=15),
        )
        BaixaFisicaBensItem.objects.create(baixa=baixa_antiga, bem=bem_baixado_antigo)
        
        criar_itens_conciliacao(conciliacao)
        # Não deve incluir o bem baixado antigo (2021 < 2022)
        self.assertFalse(ItemConciliacao.objects.filter(conciliacao=conciliacao, bem=bem_baixado_antigo).exists())

    def test_herda_situacao_em_processo_baixa_fisica(self):
        """Herda situação EM_PROCESSO_BAIXA_FISICA."""
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
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
            observacao="Em processo",
            atualizado_por=self.usuario,
        )
        OcorrenciaConciliacao.objects.create(
            item=item_antigo,
            situacao=constants.EM_PROCESSO_BAIXA_FISICA,
            observacao="Em processo",
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
        self.assertEqual(item_novo.situacao, constants.EM_PROCESSO_BAIXA_FISICA)
        self.assertEqual(item_novo.observacao, "Em processo")

    def test_herda_situacao_baixa_fisica(self):
        """Herda situação BAIXA_FISICA."""
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
            situacao=constants.BAIXA_FISICA,
            observacao="Baixa física",
            atualizado_por=self.usuario,
        )
        OcorrenciaConciliacao.objects.create(
            item=item_antigo,
            situacao=constants.BAIXA_FISICA,
            observacao="Baixa física",
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
        self.assertEqual(item_novo.situacao, constants.BAIXA_FISICA)
        self.assertEqual(item_novo.observacao, "Baixa física")

    def test_herda_encontrado_sem_divergencia_quando_anterior_encontrado(self):
        """Herda ENCONTRADO_SEM_DIVERGENCIA quando situação anterior era ENCONTRADO."""
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
            situacao=constants.ENCONTRADO,
            atualizado_por=self.usuario,
        )
        OcorrenciaConciliacao.objects.create(
            item=item_antigo,
            situacao=constants.ENCONTRADO,
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
        self.assertEqual(item_novo.situacao, constants.ENCONTRADO_SEM_DIVERGENCIA)

    def test_exclui_bens_aguardando_aprovacao(self):
        """Exclui bens aguardando aprovação."""
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        bem_aguardando = self.criar_bem(status=bem_constants.AGUARDANDO_APROVACAO)
        criar_itens_conciliacao(conciliacao)
        # Não deve incluir bem aguardando aprovação
        self.assertFalse(ItemConciliacao.objects.filter(conciliacao=conciliacao, bem=bem_aguardando).exists())

    def test_deleta_itens_anteriores_antes_de_criar_novos(self):
        """Deleta itens anteriores antes de criar novos."""
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        bem = self.criar_bem()
        # Criar item antigo
        item_antigo = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
            atualizado_por=self.usuario,
        )
        # Criar novo item (deve deletar o antigo)
        criar_itens_conciliacao(conciliacao)
        # Verificar que item antigo foi deletado
        self.assertFalse(ItemConciliacao.objects.filter(pk=item_antigo.pk).exists())
        # Verificar que novo item foi criado
        self.assertTrue(ItemConciliacao.objects.filter(conciliacao=conciliacao, bem=bem).exists())


class TestConfirmarBaixasFisicasComplementar(TestCase):
    """Testes complementares para _confirmar_baixas_fisicas_pos_conciliacao."""

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
            descricao="Desc",
            valor_unitario=100,
            marca="M",
            modelo="X",
            numero_processo="P",
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
            localizacao="Local",
        )
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def test_nao_confirma_baixa_ano_diferente(self):
        """Não confirma baixa de ano diferente."""
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate().replace(year=2024, month=6, day=15),
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
        # Criar baixa em ano diferente
        baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua,
            numero_processo_baixa="2025/001",
            status=bem_constants.ACEITA,
            criado_por=self.usuario,
            data_baixa=timezone.localdate().replace(year=2025, month=6, day=15),
        )
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=bem)
        
        n = _confirmar_baixas_fisicas_pos_conciliacao(conciliacao, self.usuario)
        self.assertEqual(n, 0)
        item.refresh_from_db()
        self.assertEqual(item.situacao, constants.EM_PROCESSO_BAIXA_FISICA)
