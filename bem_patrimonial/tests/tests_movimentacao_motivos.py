from types import SimpleNamespace

from django.test import SimpleTestCase

from bem_patrimonial import constants
from bem_patrimonial.admins.widgets.movimentacao_lote_widget import MovimentacaoLoteWidget
from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.serializers.movimentacao_serializers import motivo_impedimento_movimentacao


class MovimentacaoMotivosTestCase(SimpleTestCase):
    def test_baixa_fisica_informa_status_atual(self):
        ua = SimpleNamespace(id=10)
        bem = BemPatrimonial(
            id=52,
            sem_numeracao=False,
            numero_patrimonial="001.000000030-0",
            unidade_administrativa_id=10,
            bloqueado_conciliacao=False,
            status=constants.BAIXA_FISICA,
        )

        motivo = motivo_impedimento_movimentacao(ua, bem, set())

        self.assertIn("Baixa Física", motivo)
        self.assertIn("não pode ser movimentado", motivo)

    def test_widget_separa_modo_de_selecao_e_tipo_de_busca(self):
        html = MovimentacaoLoteWidget().render("itens_lote", "", {"id": "id_itens_lote"})

        self.assertEqual(html.count('type="radio"'), 2)
        self.assertIn('value="manual"', html)
        self.assertIn('value="todos"', html)
        self.assertIn('data-modo="geral"', html)
        self.assertIn('data-modo="faixa"', html)
        self.assertIn('Informe o número patrimonial completo do primeiro bem', html)

    def test_status_impedido_informa_status_e_aprovacao_obrigatoria(self):
        for status, rotulo in constants.STATUS:
            if status in (constants.APROVADO, constants.BAIXA_FISICA):
                continue
            with self.subTest(status=status):
                bem = BemPatrimonial(
                    id=52,
                    numero_patrimonial="001.000000030-0",
                    unidade_administrativa_id=10,
                    status=status,
                )
                motivo = motivo_impedimento_movimentacao(SimpleNamespace(id=10), bem, set())
                self.assertIn(rotulo, motivo)
                self.assertIn("não pode ser adicionado", motivo)
                self.assertIn("Somente bens com status 'Aprovado'", motivo)
