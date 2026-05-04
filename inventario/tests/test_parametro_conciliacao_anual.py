from datetime import date
from django.test import TestCase
from django.core.exceptions import ValidationError

from dados_comuns.tests.factories import criar_uo
from inventario.models import ParametroConciliacaoAnual


class ParametroConciliacaoAnualTest(TestCase):
    def setUp(self):
        self.uo = criar_uo()

    def test_criar_parametro_valido(self):
        p = ParametroConciliacaoAnual.objects.create(
            ano_referencia=2025,
            periodo_inicial=date(2026, 1, 1),
            periodo_final=date(2026, 3, 31),
            ativo=True,
            unidade_orcamentaria=self.uo,
        )
        self.assertTrue(p.pk)

    def test_nao_permite_periodo_inicial_maior_que_final(self):
        p = ParametroConciliacaoAnual(
            ano_referencia=2025,
            periodo_inicial=date(2026, 4, 1),
            periodo_final=date(2026, 3, 31),
            unidade_orcamentaria=self.uo,
        )
        with self.assertRaises(ValidationError):
            p.full_clean()

    def test_nao_permite_dois_parametros_ativos_mesmo_ano(self):
        ParametroConciliacaoAnual.objects.create(
            ano_referencia=2025,
            periodo_inicial=date(2026, 1, 1),
            periodo_final=date(2026, 3, 31),
            ativo=True,
            unidade_orcamentaria=self.uo,
        )

        p2 = ParametroConciliacaoAnual(
            ano_referencia=2025,
            periodo_inicial=date(2026, 4, 1),
            periodo_final=date(2026, 6, 30),
            ativo=True,
            unidade_orcamentaria=self.uo,
        )

        with self.assertRaises(ValidationError):
            p2.full_clean()

    def test_nao_permite_sobreposicao_de_periodos(self):
        ParametroConciliacaoAnual.objects.create(
            ano_referencia=2025,
            periodo_inicial=date(2026, 1, 1),
            periodo_final=date(2026, 3, 31),
            ativo=False,
            unidade_orcamentaria=self.uo,
        )

        p2 = ParametroConciliacaoAnual(
            ano_referencia=2025,
            periodo_inicial=date(2026, 3, 1),
            periodo_final=date(2026, 4, 30),
            ativo=False,
            unidade_orcamentaria=self.uo,
        )

        with self.assertRaises(ValidationError):
            p2.full_clean()

    def test_nao_permite_sobreposicao_de_periodos_em_anos_diferentes(self):
        ParametroConciliacaoAnual.objects.create(
            ano_referencia=2025,
            periodo_inicial=date(2026, 1, 1),
            periodo_final=date(2026, 3, 31),
            ativo=False,
            unidade_orcamentaria=self.uo,
        )

        p2 = ParametroConciliacaoAnual(
            ano_referencia=2026,
            periodo_inicial=date(2026, 3, 1),
            periodo_final=date(2026, 4, 30),
            ativo=False,
            unidade_orcamentaria=self.uo,
        )

        with self.assertRaises(ValidationError):
            p2.full_clean()
