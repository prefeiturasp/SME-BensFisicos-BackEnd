"""Testes complementares para inventario.utils_conciliacao.conciliacao_automatica."""
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from datetime import date

from inventario.models import ConciliacaoUA, ParametroConciliacaoAnual
from inventario.utils_conciliacao.conciliacao_automatica import (
    fechar_pelo_sistema,
    criar_conciliacao_anual,
    unidade_possui_bens,
    processar_conciliacao_anual_automatica,
)
from inventario import constants
from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants as bem_constants
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from django.contrib.auth.models import Group


class TestConciliacaoAutomaticaComplementar(TestCase):
    """Testes complementares para funções de conciliação automática."""

    def setUp(self):
        self.uo = criar_uo()
        self.ua = criar_ua(uo=self.uo, status=UnidadeAdministrativa.ATIVA)
        self.usuario = Usuario.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )

    def _mk_bem(self, **kwargs):
        defaults = {
            "nome": "Bem Teste",
            "descricao": "Desc",
            "valor_unitario": 100,
            "marca": "M",
            "modelo": "X",
            "numero_processo": "PROC-1",
            "unidade_administrativa": self.ua,
            "criado_por": self.usuario,
            "status": bem_constants.APROVADO,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def test_fechar_pelo_sistema(self):
        """fechar_pelo_sistema fecha conciliação corretamente."""
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        fechar_pelo_sistema(conciliacao)
        conciliacao.refresh_from_db()
        self.assertEqual(conciliacao.status, constants.CONCILIACAO_FECHADO_ADMIN)
        self.assertIsNone(conciliacao.fechado_por)
        self.assertIsNotNone(conciliacao.fechado_em)

    def test_unidade_possui_bens_com_bens(self):
        """unidade_possui_bens retorna True quando UA tem bens."""
        self._mk_bem()
        self.assertTrue(unidade_possui_bens(self.ua))

    def test_unidade_possui_bens_sem_bens(self):
        """unidade_possui_bens retorna False quando UA não tem bens."""
        self.assertFalse(unidade_possui_bens(self.ua))

    @patch('inventario.utils_conciliacao.conciliacao_automatica.criar_itens_conciliacao')
    def test_criar_conciliacao_anual_com_bens(self, mock_criar_itens):
        """criar_conciliacao_anual cria conciliação quando UA tem bens."""
        self._mk_bem()
        ano_referencia = timezone.localdate().year - 1
        criar_conciliacao_anual(self.ua, ano_referencia)
        self.assertTrue(
            ConciliacaoUA.objects.filter(
                unidade_administrativa=self.ua,
                tipo=constants.CONCILIACAO_ANUAL,
                periodo_final=date(ano_referencia, 12, 31),
            ).exists()
        )
        mock_criar_itens.assert_called_once()

    def test_criar_conciliacao_anual_sem_bens(self):
        """criar_conciliacao_anual não cria conciliação quando UA não tem bens."""
        ano_referencia = timezone.localdate().year - 1
        criar_conciliacao_anual(self.ua, ano_referencia)
        self.assertFalse(
            ConciliacaoUA.objects.filter(
                unidade_administrativa=self.ua,
                tipo=constants.CONCILIACAO_ANUAL,
            ).exists()
        )

    def test_criar_conciliacao_anual_nao_duplica(self):
        """criar_conciliacao_anual não cria conciliação duplicada."""
        self._mk_bem()
        ano_referencia = timezone.localdate().year - 1
        criar_conciliacao_anual(self.ua, ano_referencia)
        # Tentar criar novamente
        criar_conciliacao_anual(self.ua, ano_referencia)
        # Deve haver apenas uma conciliação
        self.assertEqual(
            ConciliacaoUA.objects.filter(
                unidade_administrativa=self.ua,
                tipo=constants.CONCILIACAO_ANUAL,
                periodo_final=date(ano_referencia, 12, 31),
            ).count(),
            1
        )

    @patch('inventario.utils_conciliacao.conciliacao_automatica.criar_conciliacao_anual')
    def test_processar_conciliacao_anual_automatica_gestor_com_ua(self, mock_criar):
        """processar_conciliacao_anual_automatica processa UA do gestor."""
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        gestor = Usuario.objects.create_user(
            username="gestor",
            password="x",
            email="gestor@test.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        gestor.groups.add(grupo_gestor)
        
        # Criar parâmetro para o período atual
        hoje = timezone.localdate()
        ano_corrente = hoje.year
        ano_referencia = ano_corrente - 1
        ParametroConciliacaoAnual.objects.create(
            unidade_orcamentaria=self.uo,
            ano_referencia=ano_referencia,
            periodo_inicial=date(ano_corrente, 1, 1),
            periodo_final=date(ano_corrente, 3, 31),
            ativo=True,
        )
        
        processar_conciliacao_anual_automatica(gestor)
        # Deve chamar criar_conciliacao_anual para a UA do gestor
        mock_criar.assert_called_once_with(self.ua, ano_referencia)

    @patch('inventario.utils_conciliacao.conciliacao_automatica.criar_conciliacao_anual')
    def test_processar_conciliacao_anual_automatica_gestor_sem_ua(self, mock_criar):
        """processar_conciliacao_anual_automatica processa todas UAs para gestor sem UA."""
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        gestor = Usuario.objects.create_user(
            username="gestor",
            password="x",
            email="gestor@test.com",
            unidade_administrativa=None,
            unidade_orcamentaria=self.uo,
        )
        gestor.groups.add(grupo_gestor)
        
        ua2 = criar_ua(uo=self.uo, status=UnidadeAdministrativa.ATIVA)
        
        # Criar parâmetro para o período atual
        hoje = timezone.localdate()
        ano_corrente = hoje.year
        ano_referencia = ano_corrente - 1
        ParametroConciliacaoAnual.objects.create(
            unidade_orcamentaria=self.uo,
            ano_referencia=ano_referencia,
            periodo_inicial=date(ano_corrente, 1, 1),
            periodo_final=date(ano_corrente, 3, 31),
            ativo=True,
        )
        
        processar_conciliacao_anual_automatica(gestor)
        # Deve chamar criar_conciliacao_anual para todas UAs ativas
        self.assertGreaterEqual(mock_criar.call_count, 1)

    def test_processar_conciliacao_anual_automatica_operador_sem_ua(self):
        """processar_conciliacao_anual_automatica retorna sem processar para operador sem UA."""
        grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
        operador = Usuario.objects.create_user(
            username="operador",
            password="x",
            email="operador@test.com",
            unidade_administrativa=None,
            unidade_orcamentaria=self.uo,
        )
        operador.groups.add(grupo_operador)
        
        with patch('inventario.utils_conciliacao.conciliacao_automatica.criar_conciliacao_anual') as mock_criar:
            processar_conciliacao_anual_automatica(operador)
            mock_criar.assert_not_called()

    @patch('inventario.utils_conciliacao.conciliacao_automatica.fechar_pelo_sistema')
    @patch('inventario.utils_conciliacao.conciliacao_automatica.criar_conciliacao_anual')
    def test_processar_conciliacao_anual_automatica_fecha_eventual_aberta(self, mock_criar, mock_fechar):
        """processar_conciliacao_anual_automatica fecha eventual aberta antes de criar anual."""
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        gestor = Usuario.objects.create_user(
            username="gestor",
            password="x",
            email="gestor@test.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        gestor.groups.add(grupo_gestor)
        
        # Criar eventual aberta
        eventual = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        
        # Criar parâmetro para o período atual
        hoje = timezone.localdate()
        ano_corrente = hoje.year
        ano_referencia = ano_corrente - 1
        ParametroConciliacaoAnual.objects.create(
            unidade_orcamentaria=self.uo,
            ano_referencia=ano_referencia,
            periodo_inicial=date(ano_corrente, 1, 1),
            periodo_final=date(ano_corrente, 3, 31),
            ativo=True,
        )
        
        processar_conciliacao_anual_automatica(gestor)
        # Deve fechar a eventual antes de criar a anual
        mock_fechar.assert_called_once_with(eventual)
        mock_criar.assert_called_once()

    @patch('inventario.utils_conciliacao.conciliacao_automatica.fechar_pelo_sistema')
    def test_processar_conciliacao_anual_automatica_fecha_anual_apos_periodo(self, mock_fechar):
        """processar_conciliacao_anual_automatica fecha anual aberta após período."""
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        gestor = Usuario.objects.create_user(
            username="gestor",
            password="x",
            email="gestor@test.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        gestor.groups.add(grupo_gestor)
        
        # Criar anual aberta
        ano_referencia = timezone.localdate().year - 1
        anual = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_ANUAL,
            periodo_final=date(ano_referencia, 12, 31),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        
        # Criar parâmetro com período já passado
        hoje = timezone.localdate()
        ano_corrente = hoje.year
        ParametroConciliacaoAnual.objects.create(
            unidade_orcamentaria=self.uo,
            ano_referencia=ano_referencia,
            periodo_inicial=date(ano_corrente, 1, 1),
            periodo_final=date(ano_corrente, 1, 15),  # Período já passado
            ativo=True,
        )
        
        # Mockar hoje para estar após o período
        with patch('inventario.utils_conciliacao.conciliacao_automatica.timezone.localdate') as mock_date:
            mock_date.return_value = date(ano_corrente, 2, 1)
            processar_conciliacao_anual_automatica(gestor)
            # Deve fechar a anual aberta
            mock_fechar.assert_called_once_with(anual)
