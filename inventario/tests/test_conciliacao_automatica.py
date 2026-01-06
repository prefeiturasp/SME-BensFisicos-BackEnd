from unittest.mock import PropertyMock, patch
from datetime import date
from django.test import TestCase
from django.utils import timezone

from bem_patrimonial.models import BemPatrimonial
from dados_comuns.models import UnidadeAdministrativa
from inventario.utils_conciliacao.conciliacao_automatica import (
    processar_conciliacao_anual_automatica
)
from inventario.models import ConciliacaoUA, ParametroConciliacaoAnual
from inventario import constants
from bem_patrimonial import constants as bens_constants
from usuario.models import Usuario


class ConciliacaoAutomaticaTest(TestCase):

    def setUp(self):
        self.ua = UnidadeAdministrativa.objects.create(
            codigo="001.0002", sigla="UA2", nome="Unidade Auto"
        )
        self.usuario = Usuario.objects.create_user(
            username="gestor", password="123"
        )

    @patch.object(
        Usuario,
        "is_gestor_patrimonio",
        new_callable=PropertyMock,
        return_value=True,
    )
    def test_nao_cria_conciliacao_se_nao_tiver_bens(self, mock_gestor):
        processar_conciliacao_anual_automatica(self.usuario)
        self.assertEqual(ConciliacaoUA.objects.count(), 0)

    @patch.object(
        Usuario,
        "is_gestor_patrimonio",
        new_callable=PropertyMock,
        return_value=True,
    )
    def test_cria_conciliacao_anual_dentro_do_periodo(self, mock_gestor):

        BemPatrimonial.objects.create(
            numero_patrimonial="001.000000010-0",
            nome="Bem",
            valor_unitario=100,
            status=bens_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )

        ano_ref = timezone.localdate().year - 1

        ParametroConciliacaoAnual.objects.create(
            ano_referencia=ano_ref,
            periodo_inicial=timezone.localdate() - timezone.timedelta(days=1),
            periodo_final=timezone.localdate() + timezone.timedelta(days=1),
            ativo=True,
        )

        processar_conciliacao_anual_automatica(self.usuario)

        self.assertTrue(
            ConciliacaoUA.objects.filter(
                unidade_administrativa=self.ua,
                tipo=constants.CONCILIACAO_ANUAL,
                periodo_final=date(ano_ref, 12, 31),
            ).exists()
        )