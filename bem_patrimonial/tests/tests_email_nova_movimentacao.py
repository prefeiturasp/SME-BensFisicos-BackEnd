from django.test import TestCase
from unittest.mock import patch
from django.contrib.auth.models import Group
import datetime

from bem_patrimonial.models import (
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
    UnidadeAdministrativaBemPatrimonial,
)
from bem_patrimonial.constants import APROVADO
from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario
from usuario.constants import GRUPO_OPERADOR_INVENTARIO


class EmailNovaMovimentacaoTestCase(TestCase):

    def setUp(self):
        self.ua_origem = UnidadeAdministrativa.objects.create(
            nome="DRE Centro", codigo="01.16.10.500", sigla="DRE-CENTRO"
        )
        self.ua_destino = UnidadeAdministrativa.objects.create(
            nome="MEMORIAL", codigo="01.16.10.600", sigla="MEMORIAL"
        )

        grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)

        self.operador_origem = Usuario.objects.create_user(
            username="operador_origem",
            email="origem@test.com",
            nome="Operador Origem",
            password="test123",
            unidade_administrativa=self.ua_origem,
        )
        self.operador_origem.groups.add(grupo_operador)

        self.operador_destino_1 = Usuario.objects.create_user(
            username="operador_destino_1",
            email="destino1@test.com",
            nome="Operador Destino 1",
            password="test123",
            unidade_administrativa=self.ua_destino,
            is_active=True,
        )
        self.operador_destino_1.groups.add(grupo_operador)

        self.operador_destino_2 = Usuario.objects.create_user(
            username="operador_destino_2",
            email="destino2@test.com",
            nome="Operador Destino 2",
            password="test123",
            unidade_administrativa=self.ua_destino,
            is_active=True,
        )
        self.operador_destino_2.groups.add(grupo_operador)

        self.bem = BemPatrimonial.objects.create(
            nome="POLTRONA GIRATÓRIA",
            numero_patrimonial="001.053719507-5",
            data_compra_entrega=datetime.date.today(),
            origem="aquisicao_direta",
            marca="Marca Teste",
            modelo="Modelo Teste",
            quantidade=10,
            descricao="Descrição teste",
            valor_unitario=1500.00,
            numero_processo=123456,
            criado_por=self.operador_origem,
            status=APROVADO,
        )

        UnidadeAdministrativaBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa=self.ua_origem,
            quantidade=10,
        )

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_email_enviado_para_todos_operadores_ua_destino(self, mock_send_email):
        MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args[0]
        emails_destinatarios = call_args[3]

        self.assertIn("destino1@test.com", emails_destinatarios)
        self.assertIn("destino2@test.com", emails_destinatarios)
        self.assertEqual(len(emails_destinatarios), 2)

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_template_email_conforme_especificacao(self, mock_send_email):
        MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args[0]
        subject = call_args[0]
        dict_params = call_args[1]

        self.assertEqual(subject, "[Bens Físicos] Movimentação recebida para aceite")
        self.assertIn("01.16.10.600 – MEMORIAL", dict_params["subtitle"])
        self.assertIn("001.053719507-5 – POLTRONA GIRATÓRIA", dict_params["subtitle"])
        self.assertIn("recebeu a movimentação", dict_params["subtitle"])
        self.assertIn("para aceite", dict_params["subtitle"])

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_email_nao_enviado_para_usuarios_inativos(self, mock_send_email):
        self.operador_destino_2.is_active = False
        self.operador_destino_2.save()

        MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args[0]
        emails_destinatarios = call_args[3]

        self.assertIn("destino1@test.com", emails_destinatarios)
        self.assertNotIn("destino2@test.com", emails_destinatarios)
        self.assertEqual(len(emails_destinatarios), 1)

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_email_com_numero_patrimonial_vazio(self, mock_send_email):
        self.bem.numero_patrimonial = None
        self.bem.save()

        MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args[0]
        dict_params = call_args[1]

        self.assertIn("POLTRONA GIRATÓRIA", dict_params["subtitle"])
        self.assertNotIn("None", dict_params["subtitle"])

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_email_com_codigo_ua_vazio(self, mock_send_email):
        self.ua_destino.codigo = ""
        self.ua_destino.save()

        MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args[0]
        dict_params = call_args[1]

        self.assertIn("MEMORIAL", dict_params["subtitle"])
        self.assertNotIn("01.16.10.600 MEMORIAL", dict_params["subtitle"])

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_email_nao_enviado_quando_nenhum_usuario_ativo(self, mock_send_email):
        self.operador_destino_1.is_active = False
        self.operador_destino_1.save()
        self.operador_destino_2.is_active = False
        self.operador_destino_2.save()

        MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

        mock_send_email.assert_not_called()

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_email_filtra_usuarios_sem_email(self, mock_send_email):
        self.operador_destino_2.email = ""
        self.operador_destino_2.save()

        MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args[0]
        emails_destinatarios = call_args[3]

        self.assertIn("destino1@test.com", emails_destinatarios)
        self.assertEqual(len(emails_destinatarios), 1)

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_email_nao_enviado_se_todos_sem_email(self, mock_send_email):
        self.operador_destino_1.email = ""
        self.operador_destino_1.save()
        self.operador_destino_2.email = ""
        self.operador_destino_2.save()

        MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

        mock_send_email.assert_not_called()

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_email_usa_template_correto(self, mock_send_email):
        MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            quantidade=5,
            solicitado_por=self.operador_origem,
        )

        mock_send_email.assert_called_once()
        call_args = mock_send_email.call_args[0]
        template = call_args[2]

        self.assertEqual(template, "simple_message.html")
