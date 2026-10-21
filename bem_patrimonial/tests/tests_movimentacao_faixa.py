from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError
from bem_patrimonial import constants

from bem_patrimonial.serializers.movimentacao_serializers import (
    BuscaBensMovimentacaoSerializer,
    MovimentacaoBensItemCreateSerializer,
    _dados_numero_patrimonial,
    _filtrar_intervalo_patrimonial,
    _numeros_patrimoniais_da_faixa,
    _resolver_bens_da_faixa,
    buscar_bens_para_movimentacao,
    motivo_impedimento_movimentacao,
)


MODULO = "bem_patrimonial.serializers.movimentacao_serializers"


class MovimentacaoFaixaTestCase(SimpleTestCase):
    def resolver(self, numeros, faixa, ids_aptos=None):
        bens = [SimpleNamespace(id=indice, numero_patrimonial=numero)
                for indice, numero in enumerate(numeros, start=1)]
        consulta = Mock()
        consulta.filter.return_value = consulta
        consulta.order_by.return_value = bens
        aptos = [bem.id for bem in bens] if ids_aptos is None else ids_aptos
        with patch(f"{MODULO}.BemPatrimonial.objects.filter", return_value=consulta), patch(
            f"{MODULO}.queryset_bens_movimentaveis"
        ) as movimentaveis:
            movimentaveis.return_value.filter.return_value.values_list.return_value = aptos
            return _resolver_bens_da_faixa(1, faixa)

    def test_calcula_sequencia_sem_incrementar_digito(self):
        quantidade, numeros = _numeros_patrimoniais_da_faixa(
            _dados_numero_patrimonial("001.000000010-9"),
            _dados_numero_patrimonial("001.000000012-1"),
        )
        self.assertEqual(quantidade, 3)
        self.assertEqual(numeros, ["001.000000010-9", "001.000000011-9", "001.000000012-9"])

    def test_filtra_incluindo_todos_os_digitos_dos_extremos(self):
        consulta = Mock()
        _filtrar_intervalo_patrimonial(consulta, "001.000000010-9", "001.000000012-0")
        consulta.filter.assert_called_once_with(
            sem_numeracao=False,
            numero_patrimonial__regex=r"^\d{3}\.\d{9}-\d$",
            numero_patrimonial__gte="001.000000010-0",
            numero_patrimonial__lte="001.000000012-9",
        )

    def test_preserva_ids_diferentes_com_mesmo_corpo(self):
        bens = self.resolver(
            ["001.000000010-9", "001.000000011-1", "001.000000012-0", "001.000000012-7"],
            {"numero_patrimonial_de": "001.000000010-0", "numero_patrimonial_ate": "001.000000012-0"},
        )
        self.assertEqual([bem.id for bem in bens], [1, 2, 3, 4])

    def test_continua_rejeitando_numero_ausente_no_meio(self):
        with self.assertRaisesMessage(ValidationError, "001.000000011-0"):
            self.resolver(["001.000000010-9", "001.000000012-7"], {
                "numero_patrimonial_de": "001.000000010-0",
                "numero_patrimonial_ate": "001.000000012-0",
            })

    def test_continua_rejeitando_faixa_com_bem_impedido(self):
        with self.assertRaisesMessage(ValidationError, "001.000000011-1"):
            self.resolver(["001.000000010-9", "001.000000011-1"], {
                "numero_patrimonial_de": "001.000000010-0",
                "numero_patrimonial_ate": "001.000000011-0",
            }, ids_aptos=[1])

    def test_de_sozinho_consulta_numero_exato(self):
        with patch(f"{MODULO}._buscar_e_validar_bens_da_faixa", return_value=[]) as buscar:
            _resolver_bens_da_faixa(1, {"numero_patrimonial_de": "001.000000010-9"})
        buscar.assert_called_once_with(
            1, "001.000000010-9", "001.000000010-9", ["001.000000010-9"], False,
        )

    def test_rejeita_faixa_enorme_antes_de_consultar_banco(self):
        with patch(f"{MODULO}._buscar_e_validar_bens_da_faixa") as buscar:
            with self.assertRaisesMessage(ValidationError, "no máximo 500 bens"):
                _resolver_bens_da_faixa(1, {
                    "numero_patrimonial_de": "001.000000001-0",
                    "numero_patrimonial_ate": "999.999999999-9",
                })
        buscar.assert_not_called()


class MovimentacaoBuscaTestCase(SimpleTestCase):
    def test_item_da_movimentacao_recebe_id_do_bem_e_nao_numero_patrimonial(self):
        bem = SimpleNamespace(id=10, numero_patrimonial=None)
        consulta = Mock()
        consulta.get.return_value = bem
        serializer = MovimentacaoBensItemCreateSerializer(data={"bem": 10})
        with patch.object(serializer.fields["bem"], "get_queryset", return_value=consulta):
            self.assertTrue(serializer.is_valid(), serializer.errors)
        consulta.get.assert_called_once_with(pk=10)
        self.assertIs(serializer.validated_data["bem"], bem)

    def test_ausencia_de_numero_nao_acrescenta_bloqueio_a_regra_atual(self):
        bem = SimpleNamespace(id=10, sem_numeracao=True, numero_patrimonial=None,
                              unidade_administrativa_id=1, bloqueado_conciliacao=False,
                              status=constants.APROVADO)
        self.assertIsNone(motivo_impedimento_movimentacao(SimpleNamespace(id=1), bem, set()))

    def test_serializer_aceita_consulta_sem_filtro_e_termo_em_branco(self):
        serializer = BuscaBensMovimentacaoSerializer(context={"request": Mock()})
        self.assertEqual(serializer.fields["termo_busca"].run_validation("   "), "")
        parametros = {"unidade_administrativa_origem": 1, "pagina": 1}
        with patch(f"{MODULO}.validar_ua_origem_movimentacao"):
            self.assertEqual(serializer.validate(parametros), parametros)

    def test_serializer_nao_aceita_dois_filtros_preenchidos(self):
        serializer = BuscaBensMovimentacaoSerializer(context={"request": Mock()})
        with patch(f"{MODULO}.validar_ua_origem_movimentacao"):
            with self.assertRaisesMessage(ValidationError, "apenas um critério"):
                serializer.validate({"unidade_administrativa_origem": 1, "id": 2,
                                     "termo_busca": "mesa"})

    def test_consulta_sem_filtro_preserva_escopo_e_motivos_dos_impedidos(self):
        consulta = MagicMock()
        consulta.count.return_value = 2
        consulta.order_by.return_value.__getitem__.return_value = [
            SimpleNamespace(id=indice, numero_patrimonial=f"001.00000000{indice}-0",
                            sem_numeracao=False, nome="Mesa", descricao="Mesa escolar",
                            localizacao="Sala 1")
            for indice in (1, 2)
        ]
        with patch(f"{MODULO}.BemPatrimonial.objects.filter", return_value=consulta) as bens, patch(
            f"{MODULO}.MovimentacaoBensItem.objects.filter"
        ) as pendentes, patch(
            f"{MODULO}.motivo_impedimento_movimentacao", side_effect=[None, "Baixa Física"]
        ):
            pendentes.return_value.values_list.return_value = []
            resposta = buscar_bens_para_movimentacao({
                "unidade_administrativa_origem": 1, "pagina": 1,
            })
        bens.assert_called_once_with(unidade_administrativa=1)
        consulta.filter.assert_not_called()
        self.assertEqual(resposta["count"], 2)
        self.assertTrue(resposta["itens"][0]["apto"])
        self.assertFalse(resposta["itens"][1]["apto"])
        self.assertEqual(resposta["itens"][1]["motivo"], "Baixa Física")
