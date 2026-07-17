from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from bem_patrimonial import constants
from bem_patrimonial.models import BemPatrimonial, TransferenciaBemPatrimonial
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria


class SeedTransferenciasDemoCommandTestCase(TestCase):
    def _executar_command(self):
        saida = StringIO()
        call_command("seed_transferencias_demo", stdout=saida)
        return saida.getvalue()

    def test_command_cria_massa_demo_para_transferencias(self):
        saida = self._executar_command()

        self.assertIn("Seed de transferências concluído", saida)

        self.assertTrue(
            UnidadeOrcamentaria.objects.filter(
                codigo__in={"01.16.90", "02.20.90", "03.20.90", "04.20.90"}
            ).exists()
        )
        self.assertEqual(
            UnidadeAdministrativa.objects.filter(
                codigo__in={
                    "01.16.90.001",
                    "01.16.90.002",
                    "02.20.90.001",
                    "03.20.90.001",
                    "04.20.90.001",
                }
            ).count(),
            5,
        )

        bens_demo = BemPatrimonial.objects.filter(
            numero_patrimonial__in={
                "900.000.001-1",
                "900.000.002-2",
                "900.000.003-3",
                "900.000.004-4",
                "900.000.005-5",
                "900.000.006-6",
            }
        )
        self.assertEqual(bens_demo.count(), 6)
        self.assertTrue(bens_demo.filter(status=constants.TRANSFERIDO).count() >= 2)
        self.assertTrue(
            TransferenciaBemPatrimonial.objects.filter(
                numero_processo__startswith="SEED-TRF-"
            ).count()
            >= 3
        )
        self.assertTrue(
            TransferenciaBemPatrimonial.objects.filter(
                numero_processo__startswith="SEED-TRF-",
                numero_ntbpm__isnull=False,
            ).exists()
        )

    def test_command_e_idempotente(self):
        self._executar_command()

        quantidade_uos = UnidadeOrcamentaria.objects.filter(
            codigo__in={"01.16.90", "02.20.90", "03.20.90", "04.20.90"}
        ).count()
        quantidade_uas = UnidadeAdministrativa.objects.filter(
            codigo__in={
                "01.16.90.001",
                "01.16.90.002",
                "02.20.90.001",
                "03.20.90.001",
                "04.20.90.001",
            }
        ).count()
        quantidade_bens = BemPatrimonial.objects.filter(
            numero_patrimonial__startswith="900.000."
        ).count()
        quantidade_transferencias = TransferenciaBemPatrimonial.objects.filter(
            numero_processo__startswith="SEED-TRF-"
        ).count()

        self._executar_command()

        self.assertEqual(
            UnidadeOrcamentaria.objects.filter(
                codigo__in={"01.16.90", "02.20.90", "03.20.90", "04.20.90"}
            ).count(),
            quantidade_uos,
        )
        self.assertEqual(
            UnidadeAdministrativa.objects.filter(
                codigo__in={
                    "01.16.90.001",
                    "01.16.90.002",
                    "02.20.90.001",
                    "03.20.90.001",
                    "04.20.90.001",
                }
            ).count(),
            quantidade_uas,
        )
        self.assertEqual(
            BemPatrimonial.objects.filter(numero_patrimonial__startswith="900.000.").count(),
            quantidade_bens,
        )
        self.assertEqual(
            TransferenciaBemPatrimonial.objects.filter(
                numero_processo__startswith="SEED-TRF-"
            ).count(),
            quantidade_transferencias,
        )
