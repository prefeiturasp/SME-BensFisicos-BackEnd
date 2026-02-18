from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from dados_comuns.models import UnidadeAdministrativa
from bem_patrimonial.models import BemPatrimonial

from usuario.management.commands.seed_bensfisicos_demo import (
    get_model,
    has_field,
    first_fk_to,
)


class TestSeedBensfisicosDemoHelpers(TestCase):
    def test_get_model_existente_retorna_model(self):
        model = get_model("dados_comuns.UnidadeAdministrativa")
        self.assertIsNotNone(model)
        self.assertEqual(model, UnidadeAdministrativa)

    def test_get_model_bem_patrimonial(self):
        model = get_model("bem_patrimonial.BemPatrimonial")
        self.assertIsNotNone(model)
        self.assertEqual(model, BemPatrimonial)

    def test_get_model_invalido_retorna_none(self):
        model = get_model("app_inexistente.ModeloX")
        self.assertIsNone(model)

    def test_has_field_true(self):
        self.assertTrue(has_field(UnidadeAdministrativa, "nome"))
        self.assertTrue(has_field(UnidadeAdministrativa, "sigla"))
        self.assertTrue(has_field(BemPatrimonial, "unidade_administrativa"))

    def test_has_field_false(self):
        self.assertFalse(has_field(UnidadeAdministrativa, "campo_inexistente"))
        self.assertFalse(has_field(BemPatrimonial, "xyz"))

    def test_first_fk_to_retorna_fk(self):
        fk = first_fk_to(BemPatrimonial, UnidadeAdministrativa)
        self.assertIsNotNone(fk)
        self.assertEqual(fk.name, "unidade_administrativa")

    def test_first_fk_to_model_none_retorna_none(self):
        self.assertIsNone(first_fk_to(None, UnidadeAdministrativa))
        self.assertIsNone(first_fk_to(BemPatrimonial, None))

    def test_first_fk_to_sem_fk_retorna_none(self):
        from django.contrib.contenttypes.models import ContentType
        fk = first_fk_to(ContentType, UnidadeAdministrativa)
        self.assertIsNone(fk)


class TestSeedBensfisicosDemoCommand(TestCase):
    def test_handle_sem_model_ua_raise_command_error(self):
        out = StringIO()
        with patch("usuario.management.commands.seed_bensfisicos_demo.get_model") as mock_get:
            mock_get.return_value = None
            with self.assertRaises(CommandError) as ctx:
                call_command("seed_bensfisicos_demo", stdout=out)
            self.assertIn("Model não encontrado", str(ctx.exception))

    def test_handle_sem_model_bem_raise_command_error(self):
        out = StringIO()
        def get_model_side_effect(label):
            if label == "dados_comuns.UnidadeAdministrativa":
                return UnidadeAdministrativa
            return None
        with patch("usuario.management.commands.seed_bensfisicos_demo.get_model", side_effect=get_model_side_effect):
            with self.assertRaises(CommandError) as ctx:
                call_command("seed_bensfisicos_demo", stdout=out)
            self.assertIn("Model não encontrado", str(ctx.exception))
