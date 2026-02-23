"""Testes para dados_comuns.utils."""
from django.test import TestCase

from dados_comuns.utils import repr_value, dict_changes
from dados_comuns.tests.factories import criar_uo


class TestReprValue(TestCase):
    """Testes para repr_value."""

    def test_repr_value_none(self):
        """repr_value com None retorna string vazia."""
        self.assertEqual(repr_value(None), "")

    def test_repr_value_str(self):
        """repr_value com string retorna a própria string."""
        self.assertEqual(repr_value("hello"), "hello")

    def test_repr_value_int(self):
        """repr_value com int retorna str do valor."""
        self.assertEqual(repr_value(42), "42")

    def test_repr_value_model(self):
        """repr_value com Model retorna pk - str(model)."""
        uo = criar_uo(codigo="501")
        result = repr_value(uo)
        self.assertIn(str(uo.pk), result)
        self.assertIn(str(uo), result)

    def test_repr_value_model_sem_pk(self):
        """repr_value com instância de Model sem pk retorna str(model)."""
        from dados_comuns.models import UnidadeOrcamentaria
        uo = UnidadeOrcamentaria(codigo="999", nome="Nova", sigla="UO")
        result = repr_value(uo)
        self.assertIsInstance(result, str)


class TestDictChanges(TestCase):
    """Testes para dict_changes."""

    def test_dict_changes_sem_alteracoes(self):
        """dict_changes retorna vazio quando não há alterações."""
        class Obj:
            pass
        original = Obj()
        updated = Obj()
        original.a = 1
        original.b = "x"
        updated.a = 1
        updated.b = "x"
        changes = dict_changes(original, updated, ["a", "b"])
        self.assertEqual(changes, {})

    def test_dict_changes_com_alteracoes(self):
        """dict_changes retorna dict com campos alterados."""
        class Obj:
            pass
        original = Obj()
        updated = Obj()
        original.a = 1
        original.b = "x"
        updated.a = 2
        updated.b = "x"
        changes = dict_changes(original, updated, ["a", "b"])
        self.assertEqual(changes, {"a": ("1", "2")})

    def test_dict_changes_com_only(self):
        """dict_changes com only considera apenas esses campos."""
        class Obj:
            pass
        original = Obj()
        updated = Obj()
        original.a = 1
        original.b = "x"
        updated.a = 2
        updated.b = "y"
        changes = dict_changes(original, updated, ["a", "b"], only=["a"])
        self.assertEqual(changes, {"a": ("1", "2")})

    def test_dict_changes_com_ignore(self):
        """dict_changes com ignore não inclui esses campos."""
        class Obj:
            pass
        original = Obj()
        updated = Obj()
        original.a = 1
        original.b = "x"
        updated.a = 2
        updated.b = "x"
        changes = dict_changes(original, updated, ["a", "b"], ignore=["a"])
        self.assertEqual(changes, {})
