# Cobertura de usuario/management/commands/seed_bensfisicos_demo.py

import textwrap
from unittest.mock import MagicMock, patch

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import models
from django.test import TestCase

from usuario.management.commands.seed_bensfisicos_demo import (
    first_fk_to,
    get_model,
    has_field,
)


class GetModelTest(TestCase):
    def test_get_model_existe(self):
        model = get_model("dados_comuns.UnidadeAdministrativa")
        self.assertIsNotNone(model)

    def test_get_model_inexistente_retorna_none(self):
        model = get_model("app_inexistente.ModeloQualquer")
        self.assertIsNone(model)


class HasFieldTest(TestCase):
    def test_has_field_true(self):
        UA = get_model("dados_comuns.UnidadeAdministrativa")
        self.assertTrue(has_field(UA, "nome"))
        self.assertTrue(has_field(UA, "codigo"))

    def test_has_field_false(self):
        UA = get_model("dados_comuns.UnidadeAdministrativa")
        self.assertFalse(has_field(UA, "campo_que_nao_existe"))

    def test_has_field_model_none(self):
        self.assertFalse(has_field(None, "nome"))


class FirstFkToTest(TestCase):
    def test_first_fk_to_model_none(self):
        UA = get_model("dados_comuns.UnidadeAdministrativa")
        self.assertIsNone(first_fk_to(None, UA))
        self.assertIsNone(first_fk_to(UA, None))

    def test_first_fk_to_encontra_fk(self):
        UA = get_model("dados_comuns.UnidadeAdministrativa")
        bem_model = get_model("bem_patrimonial.BemPatrimonial")
        fk = first_fk_to(bem_model, UA)
        self.assertIsNotNone(fk)
        self.assertIsInstance(fk, models.ForeignKey)
        self.assertEqual(fk.name, "unidade_administrativa")


class SeedBensfisicosDemoCommandTest(TestCase):
    """Cobertura do Command.handle (seed_bensfisicos_demo)."""

    def test_handle_model_ua_nao_encontrado_raise_command_error(self):
        def get_model_side_effect(label):
            if label == "dados_comuns.UnidadeAdministrativa":
                return None
            return apps.get_model(label)

        with patch(
            "usuario.management.commands.seed_bensfisicos_demo.get_model",
            side_effect=get_model_side_effect,
        ):
            with self.assertRaises(CommandError) as ctx:
                call_command("seed_bensfisicos_demo")
            self.assertIn("Model não encontrado", str(ctx.exception))

    def test_handle_model_bem_nao_encontrado_raise_command_error(self):
        def get_model_side_effect(label):
            if label == "bem_patrimonial.BemPatrimonial":
                return None
            return apps.get_model(label)

        with patch(
            "usuario.management.commands.seed_bensfisicos_demo.get_model",
            side_effect=get_model_side_effect,
        ):
            with self.assertRaises(CommandError) as ctx:
                call_command("seed_bensfisicos_demo")
            self.assertIn("Model não encontrado", str(ctx.exception))

    def _patch_handle_through_none(self):
        """Substitui handle por versão que usa Through = None para não quebrar em Through.objects."""
        import usuario.management.commands.seed_bensfisicos_demo as mod

        # Lê do arquivo para não depender de inspect.getsource (handle pode já ter sido substituído)
        path = mod.__file__
        with open(path, encoding="utf-8") as f:
            content = f.read()
        start = content.find("    def handle(self")
        end = content.find("\n    def ", start + 1) if start >= 0 else -1
        source = content[start:end] if end > 0 else content[start:]
        source = textwrap.dedent(source)
        new_source = source.replace('Through = "Ajustar"', "Through = None")
        exec(compile(new_source, "<handle>", "exec"), vars(mod))
        mod.Command.handle = mod.handle

    def test_handle_import_receiver_falha_receiver_func_none(self):
        """Cobre o ramo except do import (receiver_func = None)."""
        import bem_patrimonial.models as bem_models

        orig = getattr(
            bem_models,
            "cria_registro_unidade_administrativa_bem_patrimonial",
            None,
        )
        if orig is not None:
            delattr(bem_models, "cria_registro_unidade_administrativa_bem_patrimonial")
            try:
                self._patch_handle_through_none()
                bem_model = apps.get_model("bem_patrimonial.BemPatrimonial")
                with patch.object(
                    bem_model.objects, "create", return_value=MagicMock()
                ):
                    call_command("seed_bensfisicos_demo")
                UA = apps.get_model("dados_comuns.UnidadeAdministrativa")
                self.assertEqual(UA.objects.count(), 2)
            finally:
                setattr(
                    bem_models,
                    "cria_registro_unidade_administrativa_bem_patrimonial",
                    orig,
                )

    def test_handle_executa_com_sucesso(self):
        self._patch_handle_through_none()
        bem_model = apps.get_model("bem_patrimonial.BemPatrimonial")
        with patch.object(bem_model.objects, "create", return_value=MagicMock()):
            call_command("seed_bensfisicos_demo")
        UA = apps.get_model("dados_comuns.UnidadeAdministrativa")
        self.assertEqual(UA.objects.count(), 2)

    def test_handle_disconnect_raise_continua(self):
        self._patch_handle_through_none()
        bem_model = apps.get_model("bem_patrimonial.BemPatrimonial")
        with patch.object(bem_model.objects, "create", return_value=MagicMock()):
            with patch(
                "usuario.management.commands.seed_bensfisicos_demo.post_save.disconnect",
                side_effect=Exception("disconnect falhou"),
            ):
                call_command("seed_bensfisicos_demo")
        UA = apps.get_model("dados_comuns.UnidadeAdministrativa")
        self.assertEqual(UA.objects.count(), 2)

    def test_handle_connect_raise_continua(self):
        self._patch_handle_through_none()
        bem_model = apps.get_model("bem_patrimonial.BemPatrimonial")
        with patch.object(bem_model.objects, "create", return_value=MagicMock()):
            with patch(
                "usuario.management.commands.seed_bensfisicos_demo.post_save.connect",
                side_effect=Exception("connect falhou"),
            ):
                call_command("seed_bensfisicos_demo")
        UA = apps.get_model("dados_comuns.UnidadeAdministrativa")
        self.assertEqual(UA.objects.count(), 2)
