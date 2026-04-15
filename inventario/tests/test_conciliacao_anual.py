from dados_comuns.tests.auth_test_utils import auth_kwargs
from datetime import date
import datetime
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone

from dados_comuns.tests.factories import criar_ua
from usuario.models import Usuario
from inventario.models import ConciliacaoUA, ParametroConciliacaoAnual
from inventario import constants
from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants as bem_constants

from unittest.mock import patch


class ConciliacaoAnualModelTest(TestCase):

    def setUp(self):
        self.ua = criar_ua(codigo="001.0001", sigla="UA", nome="Unidade Teste")
        self.usuario = Usuario.objects.create_user(
            username="gestor",
            **auth_kwargs("123"),
            unidade_orcamentaria=self.ua.unidade_orcamentaria,
        )

    def criar_bem(self):
        return BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-0",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )

    def _criar_parametro_anual(self, ano=2025):
        """Cria o ParametroConciliacaoAnual necessário para a validação da janela."""
        return ParametroConciliacaoAnual.objects.create(
            ano_referencia=ano,
            periodo_inicial=date(2026, 1, 1),
            periodo_final=date(2026, 3, 31),
            ativo=True,
            unidade_orcamentaria=self.ua.unidade_orcamentaria,
        )

    @patch("inventario.models.timezone")
    def test_define_periodo_final_automaticamente(self, mock_tz):
        """
        Simula criação em fevereiro de 2026, dentro da janela permitida
        para a conciliação anual de 2025 (01/01/2026 a 31/03/2026).
        """
        data_simulada = datetime.datetime(2026, 2, 15, 12, 0, 0,
                                          tzinfo=datetime.timezone.utc)
        mock_tz.now.return_value = data_simulada
        mock_tz.localdate.return_value = data_simulada.date()

        self.criar_bem()
        self._criar_parametro_anual(ano=2025)

        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_ANUAL,
            criado_por=self.usuario,
        )

        self.assertIsNotNone(conciliacao.periodo_final)

    @patch("inventario.models.timezone")
    def test_nao_permite_duas_anuais_mesmo_ano(self, mock_tz):
        """
        Simula criação em fevereiro de 2026, dentro da janela permitida
        para a conciliação anual de 2025 (01/01/2026 a 31/03/2026).
        """
        data_simulada = datetime.datetime(2026, 2, 15, 12, 0, 0,
                                          tzinfo=datetime.timezone.utc)
        mock_tz.now.return_value = data_simulada
        mock_tz.localdate.return_value = data_simulada.date()

        self.criar_bem()
        self._criar_parametro_anual(ano=2025)

        # primeira criação deve funcionar
        ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_ANUAL,
            criado_por=self.usuario,
        )

        # segunda criação deve lançar o erro esperado
        with self.assertRaises(ValidationError):
            ConciliacaoUA.objects.create(
                unidade_administrativa=self.ua,
                tipo=constants.CONCILIACAO_ANUAL,
                criado_por=self.usuario,
            )

    def test_nao_permite_criar_fora_do_periodo(self):
        self.criar_bem()

        ParametroConciliacaoAnual.objects.create(
            ano_referencia=timezone.localdate().year - 1,
            periodo_inicial=date(2020, 1, 1),
            periodo_final=date(2020, 3, 31),
            ativo=True,
            unidade_orcamentaria=self.ua.unidade_orcamentaria,
        )

        with self.assertRaises(ValidationError):
            ConciliacaoUA.objects.create(
                unidade_administrativa=self.ua,
                tipo=constants.CONCILIACAO_ANUAL,
                criado_por=self.usuario,
            )
