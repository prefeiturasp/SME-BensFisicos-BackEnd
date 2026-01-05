from datetime import date
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.utils import timezone

from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario
from inventario.models import ConciliacaoUA, ParametroConciliacaoAnual
from inventario import constants
from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants as bem_constants

class ConciliacaoAnualModelTest(TestCase):

    def setUp(self):
        self.ua = UnidadeAdministrativa.objects.create(
            codigo="001.0001", sigla="UA", nome="Unidade Teste"
        )
        self.usuario = Usuario.objects.create_user(
            username="gestor", password="123"
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

    def test_define_periodo_final_automaticamente(self):
        self.criar_bem()

        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_ANUAL,
            criado_por=self.usuario,
        )

        ano_ref = timezone.localdate().year - 1
        self.assertEqual(conciliacao.periodo_final, date(ano_ref, 12, 31))

    def test_nao_permite_duas_anuais_mesmo_ano(self):
        self.criar_bem()

        ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_ANUAL,
            criado_por=self.usuario,
        )

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
        )

        with self.assertRaises(ValidationError):
            ConciliacaoUA.objects.create(
                unidade_administrativa=self.ua,
                tipo=constants.CONCILIACAO_ANUAL,
                criado_por=self.usuario,
            )