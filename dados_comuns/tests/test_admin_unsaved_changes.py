from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.test import SimpleTestCase

from bem_patrimonial.admins.bem_patrimonial import BemPatrimonialAdmin
from bem_patrimonial.models import (
    BaixaFisicaBemPatrimonial,
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
    TransferenciaBemPatrimonial,
)
from dados_comuns.admin_mixins import UnsavedChangesAdminMixin
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria
from inventario.models import ParametroConciliacaoAnual
from usuario.models import Usuario


class UnsavedChangesAdminMixinTest(SimpleTestCase):
    def setUp(self):
        self.model_admin = BemPatrimonialAdmin(BemPatrimonial, admin.site)

    def test_bem_admin_adota_protecao_reutilizavel(self):
        self.assertIsInstance(self.model_admin, UnsavedChangesAdminMixin)

    def test_demais_cadastros_editaveis_adotam_a_mesma_protecao(self):
        models = (
            BaixaFisicaBemPatrimonial,
            MovimentacaoBemPatrimonial,
            TransferenciaBemPatrimonial,
            UnidadeAdministrativa,
            UnidadeOrcamentaria,
            ParametroConciliacaoAnual,
            Usuario,
        )

        for model in models:
            with self.subTest(model=model.__name__):
                self.assertIsInstance(
                    admin.site._registry[model],
                    UnsavedChangesAdminMixin,
                )

    def test_media_preserva_recursos_existentes_e_adiciona_protecao(self):
        media = self.model_admin.media

        self.assertIn("admin/bem_patrimonial.js", media._js)
        self.assertIn("admin/unsaved_changes.js", media._js)
        self.assertIn("admin/bem_patrimonial.css", media._css["all"])
        self.assertIn("admin/unsaved_changes.css", media._css["all"])

    def test_localizacao_do_cadastro_multiplo_atualiza_payload_monitorado(self):
        script = (
            Path(settings.BASE_DIR) / "static" / "admin" / "bem_patrimonial.js"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "qs('.fld-loc', row)?.addEventListener('input', toPayload)",
            script,
        )

    def test_script_padroniza_textos_de_criacao_e_edicao(self):
        script = (
            Path(settings.BASE_DIR) / "static" / "admin" / "unsaved_changes.js"
        ).read_text(encoding="utf-8")

        textos = (
            "Sair sem salvar?",
            "Continuar preenchendo",
            "Descartar e sair",
            "Descartar alterações?",
            "Continuar editando",
            "Descartar alterações",
            "Descartar seleção?",
            "Manter seleção",
            "Descartar seleção",
        )
        for texto in textos:
            with self.subTest(texto=texto):
                self.assertIn(texto, script)

        self.assertIn("location.pathname.endsWith('/add/')", script)
