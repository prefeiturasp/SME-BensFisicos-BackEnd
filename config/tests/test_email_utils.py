"""Testes para config.utils.email_utils."""
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.core.mail import EmailMessage
from django.conf import settings

from config.utils.email_utils import send_email_ctrl


class TestEmailUtils(TestCase):
    """Testes para send_email_ctrl."""

    @patch('config.utils.email_utils.EmailMessage')
    @patch('config.utils.email_utils.render_to_string')
    def test_send_email_ctrl_com_email_string(self, mock_render, mock_email_class):
        """send_email_ctrl aceita email como string."""
        mock_render.return_value = "<html>Test</html>"
        mock_email_instance = MagicMock()
        mock_email_class.return_value = mock_email_instance
        
        send_email_ctrl(
            subject="Test Subject",
            dict={"var": "value"},
            template="test_template.html",
            to_email="test@example.com",
        )
        
        mock_email_class.assert_called_once()
        mock_email_instance.send.assert_called_once()

    @patch('config.utils.email_utils.EmailMessage')
    @patch('config.utils.email_utils.render_to_string')
    def test_send_email_ctrl_com_email_lista(self, mock_render, mock_email_class):
        """send_email_ctrl aceita email como lista."""
        mock_render.return_value = "<html>Test</html>"
        mock_email_instance = MagicMock()
        mock_email_class.return_value = mock_email_instance
        
        send_email_ctrl(
            subject="Test Subject",
            dict={"var": "value"},
            template="test_template.html",
            to_email=["test@example.com", "test2@example.com"],
        )
        
        mock_email_class.assert_called_once()
        mock_email_instance.send.assert_called_once()

    @patch('config.utils.email_utils.EmailMessage')
    @patch('config.utils.email_utils.render_to_string')
    def test_send_email_ctrl_com_dict_vazio(self, mock_render, mock_email_class):
        """send_email_ctrl funciona com dict vazio."""
        mock_render.return_value = "<html>Test</html>"
        mock_email_instance = MagicMock()
        mock_email_class.return_value = mock_email_instance
        
        send_email_ctrl(
            subject="Test Subject",
            dict=None,
            template="test_template.html",
            to_email="test@example.com",
        )
        
        mock_email_class.assert_called_once()
        mock_email_instance.send.assert_called_once()

    @patch('config.utils.email_utils.EmailMessage')
    @patch('config.utils.email_utils.render_to_string')
    def test_send_email_ctrl_usa_from_email_padrao(self, mock_render, mock_email_class):
        """send_email_ctrl usa DEFAULT_FROM_EMAIL quando from_email não fornecido."""
        mock_render.return_value = "<html>Test</html>"
        mock_email_instance = MagicMock()
        mock_email_class.return_value = mock_email_instance
        
        send_email_ctrl(
            subject="Test Subject",
            dict={"var": "value"},
            template="test_template.html",
            to_email="test@example.com",
        )
        
        # Verificar que from_email padrão foi usado
        call_args = mock_email_class.call_args
        self.assertEqual(call_args[0][2], settings.DEFAULT_FROM_EMAIL)

    @patch('config.utils.email_utils.EmailMessage')
    @patch('config.utils.email_utils.render_to_string')
    def test_send_email_ctrl_com_from_email_customizado(self, mock_render, mock_email_class):
        """send_email_ctrl aceita from_email customizado."""
        mock_render.return_value = "<html>Test</html>"
        mock_email_instance = MagicMock()
        mock_email_class.return_value = mock_email_instance
        
        custom_from = "custom@example.com"
        send_email_ctrl(
            subject="Test Subject",
            dict={"var": "value"},
            template="test_template.html",
            to_email="test@example.com",
            from_email=custom_from,
        )
        
        # Verificar que from_email customizado foi usado
        call_args = mock_email_class.call_args
        self.assertEqual(call_args[0][2], custom_from)

    @patch('config.utils.email_utils.EmailMessage')
    @patch('config.utils.email_utils.render_to_string')
    def test_send_email_ctrl_configura_content_subtype_html(self, mock_render, mock_email_class):
        """send_email_ctrl configura content_subtype como html."""
        mock_render.return_value = "<html>Test</html>"
        mock_email_instance = MagicMock()
        mock_email_class.return_value = mock_email_instance
        
        send_email_ctrl(
            subject="Test Subject",
            dict={"var": "value"},
            template="test_template.html",
            to_email="test@example.com",
        )
        
        # Verificar que content_subtype foi configurado
        self.assertEqual(mock_email_instance.content_subtype, 'html')

    @patch('config.utils.email_utils.EmailMessage')
    @patch('config.utils.email_utils.render_to_string')
    def test_send_email_ctrl_chama_render_to_string(self, mock_render, mock_email_class):
        """send_email_ctrl chama render_to_string com template e context."""
        mock_render.return_value = "<html>Test</html>"
        mock_email_instance = MagicMock()
        mock_email_class.return_value = mock_email_instance
        
        template = "test_template.html"
        context_dict = {"var": "value"}
        
        send_email_ctrl(
            subject="Test Subject",
            dict=context_dict,
            template=template,
            to_email="test@example.com",
        )
        
        # Verificar que render_to_string foi chamado
        mock_render.assert_called_once()
        call_args = mock_render.call_args
        self.assertEqual(call_args[0][0], template)

    @patch('config.utils.email_utils.EmailMessage')
    @patch('config.utils.email_utils.render_to_string')
    @patch('config.utils.email_utils.print')
    def test_send_email_ctrl_levanta_excecao_em_erro(self, mock_print, mock_render, mock_email_class):
        """send_email_ctrl levanta exceção quando há erro."""
        mock_render.side_effect = Exception("Erro ao renderizar")
        mock_email_instance = MagicMock()
        mock_email_class.return_value = mock_email_instance
        
        with self.assertRaises(Exception):
            send_email_ctrl(
                subject="Test Subject",
                dict={"var": "value"},
                template="test_template.html",
                to_email="test@example.com",
            )
        
        # Verificar que print foi chamado com erro
        mock_print.assert_called_once()
