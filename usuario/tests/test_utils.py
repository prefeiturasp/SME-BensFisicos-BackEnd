from unittest.mock import patch

from django.contrib.auth.models import Group, Permission
from django.test import TestCase

from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.utils import atribuir_permissao, setup_grupos_e_permissoes


class TestAtribuirPermissao(TestCase):
    """Testes para atribuir_permissao()."""

    @patch("usuario.utils.print")
    def test_adiciona_permissao_que_corresponde_ao_settings(self, mock_print):
        """Permissões cujo codename = verb + key e verb em verbs_by_key são adicionadas."""
        grupo = Group.objects.create(name="GrupoTeste")
        perm = Permission.objects.filter(codename="view_bempatrimonial").first()
        self.assertIsNotNone(perm, "Deve existir permissão view_bempatrimonial")
        settings = {"_bempatrimonial": ["view"]}
        atribuir_permissao(grupo, settings)
        grupo.refresh_from_db()
        self.assertIn(perm, grupo.permissions.all())
        mock_print.assert_called()

    @patch("usuario.utils.print")
    def test_nao_adiciona_permissao_quando_verb_nao_esta_em_verbs_by_key(self, mock_print):
        """Permissão não é adicionada se o verb não está na lista do key."""
        grupo = Group.objects.create(name="GrupoTeste2")
        settings = {"_bempatrimonial": ["view"]}  # só view, não add
        atribuir_permissao(grupo, settings)
        grupo.refresh_from_db()
        add_perm = Permission.objects.filter(codename="add_bempatrimonial").first()
        if add_perm:
            self.assertNotIn(add_perm, grupo.permissions.all())
        self.assertIn(
            Permission.objects.get(codename="view_bempatrimonial"),
            grupo.permissions.all(),
        )

    @patch("usuario.utils.print")
    def test_settings_vazio_nao_altera_grupo(self, mock_print):
        """Settings vazio não adiciona nenhuma permissão."""
        grupo = Group.objects.create(name="GrupoVazio")
        atribuir_permissao(grupo, {})
        grupo.refresh_from_db()
        self.assertEqual(grupo.permissions.count(), 0)
        mock_print.assert_not_called()

    @patch("usuario.utils.print")
    def test_key_inexistente_nao_quebra(self, mock_print):
        """Key que não corresponde a nenhuma permissão no DB não causa erro."""
        grupo = Group.objects.create(name="GrupoKeyFake")
        settings = {"_modelo_que_nao_existe": ["add", "view"]}
        atribuir_permissao(grupo, settings)
        grupo.refresh_from_db()
        self.assertEqual(grupo.permissions.count(), 0)


class TestSetupGruposEPermissoes(TestCase):
    """Testes para setup_grupos_e_permissoes()."""

    @patch("usuario.utils.print")
    def test_cria_grupos_gestor_e_operador(self, mock_print):
        """Cria ou obtém os grupos GESTOR_PATRIMONIO e OPERADOR_INVENTARIO."""
        setup_grupos_e_permissoes()
        self.assertTrue(Group.objects.filter(name=GRUPO_GESTOR_PATRIMONIO).exists())
        self.assertTrue(Group.objects.filter(name=GRUPO_OPERADOR_INVENTARIO).exists())

    @patch("usuario.utils.print")
    def test_gestor_recebe_permissoes(self, mock_print):
        """Grupo gestor tem pelo menos uma permissão após setup."""
        setup_grupos_e_permissoes()
        gestor = Group.objects.get(name=GRUPO_GESTOR_PATRIMONIO)
        self.assertGreater(gestor.permissions.count(), 0)

    @patch("usuario.utils.print")
    def test_operador_recebe_permissoes(self, mock_print):
        """Grupo operador tem pelo menos uma permissão após setup."""
        setup_grupos_e_permissoes()
        operador = Group.objects.get(name=GRUPO_OPERADOR_INVENTARIO)
        self.assertGreater(operador.permissions.count(), 0)

    @patch("usuario.utils.print")
    def test_idempotente_chamar_duas_vezes(self, mock_print):
        """Chamar setup duas vezes não quebra e mantém grupos."""
        setup_grupos_e_permissoes()
        setup_grupos_e_permissoes()
        self.assertEqual(Group.objects.filter(name=GRUPO_GESTOR_PATRIMONIO).count(), 1)
        self.assertEqual(
            Group.objects.filter(name=GRUPO_OPERADOR_INVENTARIO).count(), 1
        )
