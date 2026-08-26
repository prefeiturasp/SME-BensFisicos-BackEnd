"""
Testes do BemPatrimonialFilter para seleção múltipla de Unidades Administrativas.

Estes testes validam a lógica de filtragem inspecionando o queryset gerado pelo
django-filter (sem necessidade de acesso ao banco), cobrindo:

- retrocompatibilidade com um único valor;
- seleção de múltiplas UAs (lista separada por vírgula);
- ausência do parâmetro representando "Todas as UAs";
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


class BemPatrimonialFilterMultiplasUAsTest(SimpleTestCase):
    def test_campo_ua_usa_filtro_de_lista(self):
        campo = BemPatrimonialFilter.base_filters["unidade_administrativa"]
        self.assertIsInstance(campo, _NumberInFilter)
        self.assertEqual(campo.lookup_expr, "in")

    def test_valor_unico_mantem_compatibilidade(self):
        sql = _sql({"unidade_administrativa": "5"})
        self.assertIn("unidade_administrativa_id", sql)
        self.assertIn(" in (", sql)
        self.assertIn("5", sql)

    def test_multiplas_uas_geram_clausula_in(self):
        sql = _sql({"unidade_administrativa": "5,8"})
        self.assertIn(" in (", sql)
        self.assertIn("5", sql)
        self.assertIn("8", sql)

    def test_sem_parametro_nao_filtra_por_ua(self):
        sql = _sql({})
        self.assertNotIn(
            "unidade_administrativa_id\" in (",
            sql.replace("`", '"'),
        )

    def test_convive_com_filtro_de_status(self):
        sql = _sql({"unidade_administrativa": "5,8", "status": "aprovado"})
        self.assertIn(" in (", sql)
        self.assertIn("status", sql)
