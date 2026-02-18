from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from bem_patrimonial import constants
from bem_patrimonial.emails import envia_email_movimentacoes_pendentes_aceite
from bem_patrimonial.models import (
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
    MovimentacaoBensItem,
)
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario

COMMAND_ENVIA_PATH = (
    "bem_patrimonial.management.commands."
    "notificar_movimentacoes_pendentes_aceite."
    "envia_email_movimentacoes_pendentes_aceite"
)


class EnviaEmailMovimentacoesPendentesAceiteTestCase(TestCase):
    def setUp(self):
        self.ua_origem = criar_ua()
        self.ua_destino = criar_ua(
            nome="UA Destino", codigo="00.00.00.020", sigla="UA-D", uo=self.ua_origem.unidade_orcamentaria
        )
        self.usuario = Usuario.objects.create_user(
            username="operador",
            password="test123",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.ua_origem.unidade_orcamentaria,
        )
        self.bem = BemPatrimonial.objects.create(
            nome="CADEIRA",
            numero_patrimonial="001.000000001-0",
            marca="Marca",
            modelo="Modelo",
            descricao="Desc",
            valor_unitario=10.0,
            numero_processo="123",
            criado_por=self.usuario,
            status=constants.APROVADO,
            unidade_administrativa=self.ua_origem,
        )

    def _cria_movimentacao(self, dias_atraso=10, itens=1):
        mov = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.usuario,
            status=constants.ENVIADA,
        )
        MovimentacaoBemPatrimonial.objects.filter(pk=mov.pk).update(
            criado_em=timezone.now() - timedelta(days=dias_atraso)
        )
        for idx in range(itens):
            bem = self.bem
            if idx > 0:
                bem = BemPatrimonial.objects.create(
                    nome=f"CADEIRA {idx}",
                    numero_patrimonial=f"001.{(idx + 1):09d}-0",
                    marca="Marca",
                    modelo="Modelo",
                    descricao="Desc",
                    valor_unitario=10.0,
                    numero_processo="123",
                    criado_por=self.usuario,
                    status=constants.APROVADO,
                    unidade_administrativa=self.ua_origem,
                )
            MovimentacaoBensItem.objects.create(movimentacao=mov, bem=bem)
        return mov

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_nao_envia_sem_emails(self, mock_send):
        mov = self._cria_movimentacao()
        envia_email_movimentacoes_pendentes_aceite(self.ua_destino, [mov], [])
        mock_send.assert_not_called()

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_nao_envia_sem_movimentacoes(self, mock_send):
        envia_email_movimentacoes_pendentes_aceite(
            self.ua_destino,
            [],
            ["destino@test.com"],
        )
        mock_send.assert_not_called()

    @patch("bem_patrimonial.emails.email_utils.send_email_ctrl")
    def test_envio_monta_contexto_com_limites(self, mock_send):
        mov = self._cria_movimentacao(dias_atraso=15, itens=6)
        envia_email_movimentacoes_pendentes_aceite(
            self.ua_destino,
            [mov],
            ["destino@test.com"],
            dias_minimo=9,
            dias_urgente=30,
            max_movimentacoes=5,
            max_bens_por_mov=3,
        )

        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        subject = args[0]
        context = args[1]
        template = args[2]
        emails = args[3]

        self.assertEqual(subject, "[Bens Físicos] Movimentações pendentes de aceite")
        self.assertEqual(template, "movimentacoes_pendentes_aceite_email.html")
        self.assertEqual(emails, ["destino@test.com"])
        self.assertEqual(context["total"], 1)
        self.assertEqual(context["exibidas"], 1)
        self.assertEqual(context["mov_excedentes"], 0)
        self.assertEqual(context["total_urgentes"], 0)
        self.assertEqual(context["dias_minimo"], 9)
        self.assertEqual(context["dias_urgente"], 30)
        self.assertEqual(len(context["movimentacoes"]), 1)
        self.assertEqual(context["movimentacoes"][0]["bens_excedentes"], 3)


class NotificarMovimentacoesPendentesCommandTestCase(TestCase):
    def setUp(self):
        self.ua_origem = criar_ua(
            nome="UA Origem", codigo="00.00.00.030", sigla="UA-O"
        )
        self.ua_destino = criar_ua(uo=self.ua_origem.unidade_orcamentaria,
            nome="UA Destino", codigo="00.00.00.040", sigla="UA-D"
        )
        self.ua_destino_2 = criar_ua(uo=self.ua_origem.unidade_orcamentaria,
            nome="UA Destino 2", codigo="00.00.00.050", sigla="UA-D2"
        )
        grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)

        self.operador = Usuario.objects.create_user(
            username="operador",
            email="operador@test.com",
            password="test123",
            unidade_administrativa=self.ua_destino,
            unidade_orcamentaria=self.ua_destino.unidade_orcamentaria,
            is_active=True,
        )
        self.operador.groups.add(grupo_operador)

        self.gestor = Usuario.objects.create_user(
            username="gestor",
            email="gestor@test.com",
            password="test123",
            unidade_administrativa=self.ua_destino,
            unidade_orcamentaria=self.ua_destino.unidade_orcamentaria,
            is_active=True,
        )
        self.gestor.groups.add(grupo_gestor)

        self.sem_email = Usuario.objects.create_user(
            username="sem_email",
            email="",
            password="test123",
            unidade_administrativa=self.ua_destino_2,

            unidade_orcamentaria=self.ua_destino_2.unidade_orcamentaria,
            is_active=True,
        )
        self.sem_email.groups.add(grupo_operador)

        self.solicitante = Usuario.objects.create_user(
            username="solicitante",
            password="test123",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.ua_origem.unidade_orcamentaria,
        )

    def _cria_movimentacao(self, ua_destino, dias_atraso=10, status=constants.ENVIADA):
        mov = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=ua_destino,
            solicitado_por=self.solicitante,
            status=status,
        )
        MovimentacaoBemPatrimonial.objects.filter(pk=mov.pk).update(
            criado_em=timezone.now() - timedelta(days=dias_atraso)
        )
        return mov

    @patch(COMMAND_ENVIA_PATH)
    def test_comando_dry_run_nao_envia(self, mock_envia):
        self._cria_movimentacao(self.ua_destino)
        call_command("notificar_movimentacoes_pendentes_aceite", "--dry-run")
        mock_envia.assert_not_called()

    @patch(COMMAND_ENVIA_PATH)
    def test_comando_envia_para_ua_com_destinatarios(self, mock_envia):
        self._cria_movimentacao(self.ua_destino)
        self._cria_movimentacao(self.ua_destino_2)

        call_command("notificar_movimentacoes_pendentes_aceite")

        self.assertEqual(mock_envia.call_count, 1)
        args = mock_envia.call_args[0]
        kwargs = mock_envia.call_args.kwargs
        self.assertEqual(args[0], self.ua_destino)
        self.assertEqual(len(args[1]), 1)
        self.assertEqual(
            sorted(args[2]), sorted(["operador@test.com", "gestor@test.com"])
        )
        self.assertEqual(kwargs.get("dias_minimo"), 7)
        self.assertEqual(kwargs.get("dias_urgente"), 30)

    @patch(COMMAND_ENVIA_PATH)
    def test_comando_filtra_por_ua_codigo(self, mock_envia):
        self._cria_movimentacao(self.ua_destino)
        self._cria_movimentacao(self.ua_destino_2)

        call_command(
            "notificar_movimentacoes_pendentes_aceite",
            "--ua-codigo",
            self.ua_destino.codigo,
        )

        self.assertEqual(mock_envia.call_count, 1)
        args = mock_envia.call_args[0]
        self.assertEqual(args[0], self.ua_destino)

    @patch(COMMAND_ENVIA_PATH)
    def test_comando_filtra_por_ua_id(self, mock_envia):
        self._cria_movimentacao(self.ua_destino)
        self._cria_movimentacao(self.ua_destino_2)

        call_command(
            "notificar_movimentacoes_pendentes_aceite",
            "--ua-id",
            str(self.ua_destino_2.id),
        )

        self.assertEqual(mock_envia.call_count, 0)

    @patch(COMMAND_ENVIA_PATH)
    def test_comando_ignora_status_nao_enviada(self, mock_envia):
        self._cria_movimentacao(self.ua_destino, status=constants.ACEITA)
        call_command("notificar_movimentacoes_pendentes_aceite")
        mock_envia.assert_not_called()

    @patch(COMMAND_ENVIA_PATH)
    def test_comando_ignora_menos_de_7_dias(self, mock_envia):
        self._cria_movimentacao(self.ua_destino, dias_atraso=2)
        call_command("notificar_movimentacoes_pendentes_aceite")
        mock_envia.assert_not_called()

    @patch(COMMAND_ENVIA_PATH)
    def test_comando_sem_movimentacoes(self, mock_envia):
        call_command("notificar_movimentacoes_pendentes_aceite")
        mock_envia.assert_not_called()

    @patch(COMMAND_ENVIA_PATH)
    def test_comando_log_file(self, mock_envia):
        self._cria_movimentacao(self.ua_destino)
        with patch("builtins.open") as mock_open:
            call_command(
                "notificar_movimentacoes_pendentes_aceite",
                "--log-file",
                "/tmp/test.log",
            )
            mock_open.assert_called_once()


class TemplateMovimentacoesPendentesAceiteTestCase(TestCase):
    def test_template_render(self):
        context = {
            "subject": "Assunto",
            "ua_info": "UA Teste",
            "total": 2,
            "total_urgentes": 1,
            "mov_excedentes": 1,
            "exibidas": 1,
            "movimentacoes": [
                {
                    "id": 10,
                    "urgente": True,
                    "ua_origem": "UA Origem",
                    "data_envio": "01/01/2026",
                    "dias_pendentes": 10,
                    "bens": ["Bem A", "Bem B"],
                    "bens_excedentes": 2,
                }
            ],
            "pendentes_url": "http://example.com",
        }

        from django.template.loader import render_to_string

        html = render_to_string(
            "movimentacoes_pendentes_aceite_email.html",
            {"context": context},
        )

        self.assertIn("Movimentações pendentes de aceite", html)
        self.assertIn("UA Teste", html)
        self.assertIn("Movimentação #10", html)
        self.assertIn("Bem A", html)
        self.assertIn("+ 2 item(ns) não exibido(s)", html)
        self.assertIn("http://example.com", html)
