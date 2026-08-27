"""
Testes do BemPatrimonialFilter para seleção múltipla de Unidades.

Validam a lógica de filtragem inspecionando o queryset gerado pelo
django-filter (sem necessidade de acesso ao banco), cobrindo:

- retrocompatibilidade com um único valor de UA;
- seleção de múltiplas UAs (lista separada por vírgula);
- ausência dos parâmetros representando "Todas as UAs";
- filtro por Unidade Orçamentária (otimização: UO inteira marcada);
- união (OR) quando UA e UO são enviados juntos;
- coexistência com os demais filtros da tela.
"""

from django.test import SimpleTestCase

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.views import BemPatrimonialFilter, _NumberInFilter


def _sql(params):
    """Aplica o filtro e retorna o SQL (lowercase) do queryset resultante."""
    filterset = BemPatrimonialFilter(
        data=params,
        queryset=BemPatrimonial.objects.all(),
    )
    assert filterset.is_valid(), filterset.errors
    return str(filterset.qs.query).lower()


class BemPatrimonialFilterMultiplasUnidadesTest(SimpleTestCase):
    def test_campos_usam_filtro_de_lista(self):
        ua = BemPatrimonialFilter.base_filters["unidade_administrativa"]
        uo = BemPatrimonialFilter.base_filters["unidade_orcamentaria"]
        self.assertIsInstance(ua, _NumberInFilter)
        self.assertIsInstance(uo, _NumberInFilter)

    def test_valor_unico_de_ua_mantem_compatibilidade(self):
        sql = _sql({"unidade_administrativa": "5"})
        self.assertIn("unidade_administrativa_id", sql)
        self.assertIn(" in (", sql)
        self.assertIn("5", sql)

    def test_multiplas_uas_geram_clausula_in(self):
        sql = _sql({"unidade_administrativa": "5,8"})
        self.assertIn(" in (", sql)
        self.assertIn("5", sql)
        self.assertIn("8", sql)

    def test_sem_parametros_nao_filtra_por_unidade(self):
        sql = _sql({})
        self.assertNotIn("unidade_administrativa_id\" in (", sql.replace("`", '"'))
        self.assertNotIn("unidade_orcamentaria_id\" in (", sql.replace("`", '"'))

    def test_filtro_por_unidade_orcamentaria(self):
        sql = _sql({"unidade_orcamentaria": "3"})
        self.assertIn("unidade_orcamentaria_id", sql)
        self.assertIn(" in (", sql)
        self.assertIn("3", sql)

    def test_ua_e_uo_juntos_geram_uniao_or(self):
        sql = _sql({"unidade_administrativa": "5,8", "unidade_orcamentaria": "3"})
        # ambos os campos presentes, combinados por OR
        self.assertIn("unidade_administrativa_id", sql)
        self.assertIn("unidade_orcamentaria_id", sql)
        self.assertIn(" or ", sql)

    def test_convive_com_filtro_de_status(self):
        sql = _sql({"unidade_administrativa": "5,8", "status": "aprovado"})
        self.assertIn(" in (", sql)
        self.assertIn("status", sql)
