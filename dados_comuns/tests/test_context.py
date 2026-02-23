"""Testes para dados_comuns.context."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from dados_comuns.context import set_user, get_user, audit_as


User = get_user_model()


class TestContext(TestCase):
    """Testes para funções de contexto de thread."""

    def setUp(self):
        # Limpar contexto antes de cada teste
        set_user(None)
        self.user = User.objects.create_user(
            username="test_user",
            password="x",
            email="test@test.com",
        )

    def tearDown(self):
        # Limpar contexto após cada teste
        set_user(None)

    def test_set_user_e_get_user(self):
        """set_user e get_user funcionam corretamente."""
        # Limpar contexto antes do teste
        set_user(None)
        # Inicialmente não há usuário
        self.assertIsNone(get_user())
        
        # Define usuário
        set_user(self.user)
        self.assertEqual(get_user(), self.user)
        
        # Define None
        set_user(None)
        self.assertIsNone(get_user())

    def test_audit_as_context_manager(self):
        """audit_as funciona como context manager."""
        user2 = User.objects.create_user(
            username="user2",
            password="x",
            email="user2@test.com",
        )
        
        # Define usuário inicial
        set_user(self.user)
        self.assertEqual(get_user(), self.user)
        
        # Usa context manager
        with audit_as(user2):
            self.assertEqual(get_user(), user2)
        
        # Restaura usuário anterior após sair do contexto
        self.assertEqual(get_user(), self.user)

    def test_audit_as_restaura_anterior_apos_excecao(self):
        """audit_as restaura usuário anterior mesmo após exceção."""
        user2 = User.objects.create_user(
            username="user2",
            password="x",
            email="user2@test.com",
        )
        
        set_user(self.user)
        
        try:
            with audit_as(user2):
                self.assertEqual(get_user(), user2)
                raise ValueError("Erro de teste")
        except ValueError:
            pass
        
        # Deve ter restaurado o usuário anterior
        self.assertEqual(get_user(), self.user)

    def test_audit_as_com_none(self):
        """audit_as funciona com None."""
        set_user(self.user)
        
        with audit_as(None):
            self.assertIsNone(get_user())
        
        self.assertEqual(get_user(), self.user)
