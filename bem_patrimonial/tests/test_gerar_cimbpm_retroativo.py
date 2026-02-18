from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario

from bem_patrimonial import constants
from bem_patrimonial.models import MovimentacaoBemPatrimonial


class TestCommandGerarCimbpmRetroativo(TestCase):
    def setUp(self):
        self.uo = criar_uo()
        self.ua_origem = criar_ua(
            uo=self.uo,
            codigo="01.16.10.379",
            nome="UA Origem",
            status=UnidadeAdministrativa.ATIVA,
        )
        self.ua_destino = criar_ua(
            uo=self.uo,
            codigo="01.16.10.408",
            nome="UA Destino",
            status=UnidadeAdministrativa.ATIVA,
        )
        self.usuario = Usuario.objects.create_user(
            username="user_cimbpm",
            password="x",
            email="user@test.com",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )

    def _criar_movimentacao(self, numero_cimbpm=None, **kwargs):
        defaults = {
            "unidade_administrativa_origem": self.ua_origem,
            "unidade_administrativa_destino": self.ua_destino,
            "solicitado_por": self.usuario,
            "status": constants.ENVIADA,
            "numero_cimbpm": numero_cimbpm,
        }
        defaults.update(kwargs)
        return MovimentacaoBemPatrimonial.objects.create(**defaults)

    def test_nenhuma_movimentacao_pendente(self):
        out = StringIO()
        call_command("gerar_cimbpm_retroativo", stdout=out)
        self.assertIn("Nenhuma movimentação pendente", out.getvalue())

    def test_nenhuma_pendente_quando_todas_ja_tem_numero(self):
        self._criar_movimentacao(numero_cimbpm="379.408.0000001.2024")
        out = StringIO()
        call_command("gerar_cimbpm_retroativo", stdout=out)
        self.assertIn("Nenhuma movimentação pendente", out.getvalue())

    def test_gera_numero_para_pendentes(self):
        mov = self._criar_movimentacao(numero_cimbpm=None)
        MovimentacaoBemPatrimonial.objects.filter(pk=mov.pk).update(numero_cimbpm=None)
        mov.refresh_from_db()
        out = StringIO()
        call_command("gerar_cimbpm_retroativo", stdout=out)
        mov.refresh_from_db()
        self.assertIsNotNone(mov.numero_cimbpm)
        self.assertIn("379", mov.numero_cimbpm)
        self.assertIn("408", mov.numero_cimbpm)
        self.assertIn("processados", out.getvalue())

    def test_considera_movimentacao_com_numero_vazio(self):
        mov = self._criar_movimentacao(numero_cimbpm=None)
        MovimentacaoBemPatrimonial.objects.filter(pk=mov.pk).update(numero_cimbpm="")
        out = StringIO()
        call_command("gerar_cimbpm_retroativo", stdout=out)
        mov.refresh_from_db()
        self.assertIsNotNone(mov.numero_cimbpm)
        self.assertNotEqual(mov.numero_cimbpm, "")

    def test_limpar_zera_numeros_existentes_e_regenera(self):
        mov = self._criar_movimentacao(numero_cimbpm=None)
        MovimentacaoBemPatrimonial.objects.filter(pk=mov.pk).update(
            numero_cimbpm="379.408.0000009.2024"
        )
        mov.refresh_from_db()
        out = StringIO()
        call_command("gerar_cimbpm_retroativo", "--limpar", stdout=out)
        mov.refresh_from_db()
        self.assertIn("números limpos", out.getvalue())
        self.assertIn("processados", out.getvalue())
        self.assertIsNotNone(mov.numero_cimbpm)

    def test_limpar_depois_gera_novamente(self):
        mov = self._criar_movimentacao(numero_cimbpm=None)
        MovimentacaoBemPatrimonial.objects.filter(pk=mov.pk).update(
            numero_cimbpm="379.408.0000001.2024"
        )
        out = StringIO()
        call_command("gerar_cimbpm_retroativo", "--limpar", stdout=out)
        call_command("gerar_cimbpm_retroativo", stdout=out)
        mov.refresh_from_db()
        self.assertIsNotNone(mov.numero_cimbpm)

    def test_erro_em_uma_movimentacao_registra_erro_e_continua(self):
        mov1 = self._criar_movimentacao(numero_cimbpm=None)
        mov2 = self._criar_movimentacao(numero_cimbpm=None)
        MovimentacaoBemPatrimonial.objects.filter(pk__in=[mov1.pk, mov2.pk]).update(
            numero_cimbpm=None
        )
        mov1.refresh_from_db()
        mov2.refresh_from_db()
        out = StringIO()

        def gerar_side_effect(mov):
            if mov.id == mov2.id:
                raise ValueError("Erro simulado")
            return "379.408.0000001.2024"

        with patch("bem_patrimonial.management.commands.gerar_cimbpm_retroativo.gerar_numero_cimbpm", side_effect=gerar_side_effect):
            call_command("gerar_cimbpm_retroativo", stdout=out)
        self.assertIn("1 processados", out.getvalue())
        self.assertIn("1 erros", out.getvalue())
        self.assertIn("Erro ID", out.getvalue())
        self.assertIn("Erro simulado", out.getvalue())
        mov1.refresh_from_db()
        mov2.refresh_from_db()
        self.assertEqual(mov1.numero_cimbpm, "379.408.0000001.2024")
        self.assertIsNone(mov2.numero_cimbpm)
