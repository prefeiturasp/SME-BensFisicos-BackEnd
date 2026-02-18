from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from dados_comuns.tests.factories import criar_ua, criar_uo
from bem_patrimonial import constants
from bem_patrimonial.models import BemPatrimonial


class TestCommandRemoveNpatDaDescricao(TestCase):
    def setUp(self):
        self.uo = criar_uo()
        self.ua = criar_ua(uo=self.uo)
        self.user = None

    def _criar_bem(self, descricao="", numero_patrimonial=None, numero_formato_antigo=False, sem_numeracao=False, **kwargs):
        defaults = {
            "nome": "Bem Teste",
            "descricao": descricao,
            "valor_unitario": 100,
            "marca": "M",
            "modelo": "X",
            "numero_processo": "PROC-1",
            "unidade_administrativa": self.ua,
            "status": constants.APROVADO,
            "sem_numeracao": sem_numeracao,
            "numero_formato_antigo": numero_formato_antigo,
            "numero_patrimonial": numero_patrimonial,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def test_sem_bens_com_numero_saida_ok(self):
        out = StringIO()
        call_command("bem_patrimonial_remove_npat_da_descricao", stdout=out)
        self.assertIn("Finalizado", out.getvalue())
        self.assertIn("Verificados: 0", out.getvalue())

    def test_remove_npat_da_descricao_e_salva(self):
        npat = "001.000000001-1"
        bem = self._criar_bem(
            descricao=f"Descrição com número {npat} no meio",
            numero_patrimonial=npat,
            numero_formato_antigo=False,
            sem_numeracao=False,
        )
        out = StringIO()
        call_command("bem_patrimonial_remove_npat_da_descricao", stdout=out)
        bem.refresh_from_db()
        self.assertNotIn(npat, bem.descricao)
        self.assertIn("Descrição com número", bem.descricao)
        self.assertIn("no meio", bem.descricao)
        self.assertIn("Alterados: 1", out.getvalue())

    def test_dry_run_nao_salva(self):
        npat = "001.000000002-2"
        bem = self._criar_bem(
            descricao=f"{npat} algo",
            numero_patrimonial=npat,
            numero_formato_antigo=False,
            sem_numeracao=False,
        )
        out = StringIO()
        call_command("bem_patrimonial_remove_npat_da_descricao", "--dry-run", stdout=out)
        bem.refresh_from_db()
        self.assertEqual(bem.descricao, f"{npat} algo")
        self.assertIn("DRY RUN", out.getvalue())
        self.assertIn("nada salvo", out.getvalue())

    def test_limpa_caracteres_especiais_no_inicio(self):
        npat = "001.000000003-3"
        bem = self._criar_bem(
            descricao="***  Mesa de escritório",
            numero_patrimonial=npat,
            numero_formato_antigo=False,
            sem_numeracao=False,
        )
        out = StringIO()
        call_command("bem_patrimonial_remove_npat_da_descricao", stdout=out)
        bem.refresh_from_db()
        self.assertEqual(bem.descricao, "Mesa de escritório")

    def test_limit_processa_apenas_n(self):
        npat1 = "001.000000004-4"
        npat2 = "001.000000005-5"
        self._criar_bem(descricao=npat1, numero_patrimonial=npat1, sem_numeracao=False, numero_formato_antigo=False)
        self._criar_bem(descricao=npat2, numero_patrimonial=npat2, sem_numeracao=False, numero_formato_antigo=False)
        out = StringIO()
        call_command("bem_patrimonial_remove_npat_da_descricao", "--limit=1", stdout=out)
        count_alterados = BemPatrimonial.objects.exclude(descricao__contains="001.000000").count()
        self.assertEqual(count_alterados, 1)

    def test_numero_formato_novo_invalido_ignorado(self):
        bem = self._criar_bem(
            descricao="Numero invalido 999 na descricao",
            numero_patrimonial="999",
            numero_formato_antigo=False,
            sem_numeracao=False,
        )
        out = StringIO()
        call_command("bem_patrimonial_remove_npat_da_descricao", stdout=out)
        bem.refresh_from_db()
        self.assertEqual(bem.descricao, "Numero invalido 999 na descricao")
        self.assertIn("deveria ser formato novo", out.getvalue())
        self.assertIn("Ignorando", out.getvalue())

    def test_numero_formato_antigo_remove_da_descricao_mesmo_sem_regex(self):
        bem = self._criar_bem(
            descricao="Codigo antigo XYZ123",
            numero_patrimonial="XYZ123",
            numero_formato_antigo=True,
            sem_numeracao=False,
        )
        out = StringIO()
        call_command("bem_patrimonial_remove_npat_da_descricao", stdout=out)
        bem.refresh_from_db()
        self.assertNotIn("XYZ123", bem.descricao)
        self.assertEqual(bem.descricao, "Codigo antigo")

    def test_sem_numeracao_com_numero_remove_da_descricao(self):
        bem = self._criar_bem(
            descricao="Texto 000.111222333-4 fim",
            numero_patrimonial="000.111222333-4",
            numero_formato_antigo=False,
            sem_numeracao=True,
        )
        out = StringIO()
        call_command("bem_patrimonial_remove_npat_da_descricao", stdout=out)
        bem.refresh_from_db()
        self.assertEqual(bem.descricao, "Texto  fim")
        self.assertNotIn("000.111222333-4", bem.descricao)

    def test_apenas_caracteres_especiais_inicio_sem_npat_na_descricao(self):
        npat = "001.000000006-6"
        bem = self._criar_bem(
            descricao="   ### Cadeira",
            numero_patrimonial=npat,
            numero_formato_antigo=False,
            sem_numeracao=False,
        )
        out = StringIO()
        call_command("bem_patrimonial_remove_npat_da_descricao", stdout=out)
        bem.refresh_from_db()
        self.assertEqual(bem.descricao, "Cadeira")

    def test_bem_sem_alteracao_nao_conta_alterado(self):
        npat = "001.000000007-7"
        self._criar_bem(
            descricao="Só texto sem número",
            numero_patrimonial=npat,
            numero_formato_antigo=False,
            sem_numeracao=False,
        )
        out = StringIO()
        call_command("bem_patrimonial_remove_npat_da_descricao", stdout=out)
        self.assertIn("Verificados: 1", out.getvalue())
        self.assertIn("Alterados: 0", out.getvalue())
