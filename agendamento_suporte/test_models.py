from datetime import date, time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from dados_comuns.tests.factories import criar_ua, criar_uo

# Só importa models e define testes reais quando o app está em INSTALLED_APPS,
# para não quebrar a suíte quando agendamento_suporte estiver desabilitado.
if "agendamento_suporte" in getattr(settings, "INSTALLED_APPS", []):
    from agendamento_suporte.constants import MONDAY, TUESDAY
    from agendamento_suporte.models import (
        ConfigAgendaSuporte,
        DiaSemana,
        IntervaloHoras,
        AgendamentoSuporte,
    )


User = get_user_model()


if "agendamento_suporte" not in getattr(settings, "INSTALLED_APPS", []):

    class TestAgendamentoSuporteSkipped(TestCase):
        def test_app_not_installed(self):
            self.skipTest("agendamento_suporte não está em INSTALLED_APPS")

else:

    class TestConfigAgendaSuporte(TestCase):
        def test_str_retorna_nome(self):
            obj = ConfigAgendaSuporte(nome="Agenda Principal")
            obj.save()
            self.assertEqual(str(obj), "Agenda Principal")

        def test_clean_permite_primeira_configuracao(self):
            obj = ConfigAgendaSuporte(nome="Única")
            obj.full_clean()
            obj.save()
            self.assertEqual(ConfigAgendaSuporte.objects.count(), 1)

        def test_clean_impede_segunda_configuracao(self):
            ConfigAgendaSuporte.objects.create(nome="Primeira")
            segunda = ConfigAgendaSuporte(nome="Segunda")
            with self.assertRaises(ValidationError) as ctx:
                segunda.full_clean()
            self.assertIn("Somente 1 configuração", str(ctx.exception))

        def test_clean_permite_editar_existente(self):
            obj = ConfigAgendaSuporte.objects.create(nome="Original")
            obj.nome = "Editada"
            obj.full_clean()
            obj.save()
            obj.refresh_from_db()
            self.assertEqual(obj.nome, "Editada")

        def test_save_chama_super(self):
            obj = ConfigAgendaSuporte(nome="Teste Save")
            obj.save()
            self.assertIsNotNone(obj.pk)

    class TestDiaSemana(TestCase):
        def setUp(self):
            self.agenda = ConfigAgendaSuporte.objects.create(nome="Agenda Teste")

        def test_str_retorna_label_do_dia(self):
            dia = DiaSemana.objects.create(agenda=self.agenda, dia_semana=MONDAY)
            self.assertEqual(str(dia), "Segunda-feira")

        def test_get_day_week_display_retorna_label(self):
            dia = DiaSemana(agenda=self.agenda, dia_semana=TUESDAY)
            self.assertEqual(dia.get_day_week_display(), "Terça-feira")

        def test_get_day_week_display_quando_nao_encontra_retorna_ultimo_label(self):
            dia = DiaSemana(agenda=self.agenda, dia_semana="invalido")
            label = dia.get_day_week_display()
            self.assertEqual(label, "Domingo")

        def test_save_chama_super(self):
            dia = DiaSemana.objects.create(agenda=self.agenda, dia_semana=MONDAY)
            self.assertIsNotNone(dia.pk)

        def test_unique_together_dia_agenda(self):
            DiaSemana.objects.create(agenda=self.agenda, dia_semana=MONDAY)
            with self.assertRaises(Exception):
                DiaSemana.objects.create(agenda=self.agenda, dia_semana=MONDAY)

    class TestIntervaloHoras(TestCase):
        def setUp(self):
            self.agenda = ConfigAgendaSuporte.objects.create(nome="Agenda")
            self.dia = DiaSemana.objects.create(agenda=self.agenda, dia_semana=MONDAY)

        def test_str_formato_hora_inicio_fim(self):
            intervalo = IntervaloHoras.objects.create(
                agenda=self.dia,
                hora_inicio=time(9, 0),
                hora_fim=time(12, 0),
            )
            self.assertIn("09:00", str(intervalo))
            self.assertIn("12:00", str(intervalo))

        def test_save_chama_super(self):
            intervalo = IntervaloHoras.objects.create(
                agenda=self.dia,
                hora_inicio=time(8, 0),
                hora_fim=time(10, 0),
            )
            self.assertIsNotNone(intervalo.pk)

    class TestAgendamentoSuporte(TestCase):
        def setUp(self):
            self.uo = criar_uo()
            self.ua = criar_ua(uo=self.uo)
            self.usuario = User.objects.create_user(
                username="user_agenda",
                password="x",
                email="agenda@test.com",
                nome="Fulano",
                unidade_administrativa=self.ua,
                unidade_orcamentaria=self.uo,
            )

        def test_str_formato_nome_data_hora(self):
            ag = AgendamentoSuporte.objects.create(
                agendado_por=self.usuario,
                data_agendada=date(2025, 3, 15),
                hora_agendada=time(14, 30),
            )
            self.assertIn("Fulano", str(ag))
            self.assertIn("15/03/25", str(ag))
            self.assertIn("14:30", str(ag))

        def test_save_chama_super(self):
            ag = AgendamentoSuporte.objects.create(
                agendado_por=self.usuario,
                data_agendada=date(2025, 1, 10),
                hora_agendada=time(9, 0),
            )
            self.assertIsNotNone(ag.pk)

        def test_observacao_opcional(self):
            ag = AgendamentoSuporte.objects.create(
                agendado_por=self.usuario,
                data_agendada=date(2025, 1, 10),
                hora_agendada=time(9, 0),
                observacao="Teste",
            )
            ag.refresh_from_db()
            self.assertEqual(ag.observacao, "Teste")
