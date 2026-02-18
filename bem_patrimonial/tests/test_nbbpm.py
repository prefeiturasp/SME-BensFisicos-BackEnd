from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario

from bem_patrimonial import constants
from bem_patrimonial.models import (
    BemPatrimonial,
    BaixaFisicaBemPatrimonial,
    BaixaFisicaBensItem,
)
from bem_patrimonial.nbbpm import (
    obter_bens_baixa,
    gerar_numero_nbbpm,
    gerar_pdf_nbbpm,
    http_response_nbbpm,
)


class NBBPMTestBase(TestCase):
    def setUp(self):
        self.grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.grupo_operador, _ = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )
        self.ua_origem = criar_ua(
            codigo="01.16.10.287",
            sigla="UATEST",
            nome="Unidade Administrativa Teste",
            status=UnidadeAdministrativa.ATIVA
        )

        self.operador = Usuario.objects.create_user(
            username="operador",
            nome="João Silva",
            rf="1234567",
            email="operador@exemplo.com",
            password="senha123",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.ua_origem.unidade_orcamentaria,
        )
        self.operador.groups.add(self.grupo_operador)

        self.gestor = Usuario.objects.create_user(
            username="gestor",
            nome="Maria Santos",
            rf="7654321",
            email="gestor@exemplo.com",
            password="senha123",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.ua_origem.unidade_orcamentaria,
        )
        self.gestor.groups.add(self.grupo_gestor)

    def criar_bem(self, **kwargs):
        defaults = {
            "numero_patrimonial": "001.053370965-3",
            "nome": "Armário",
            "descricao": "Armário de madeira",
            "valor_unitario": Decimal("2038.00"),
            "marca": "MarcaTeste",
            "modelo": "ModeloTeste",
            "numero_processo": "2024/001",
            "status": constants.APROVADO,
            "unidade_administrativa": self.ua_origem,
            "criado_por": self.operador,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def criar_baixa(self, *, status=constants.ACEITA, **kwargs):
        defaults = {
            "unidade_administrativa_origem": self.ua_origem,
            "numero_processo_baixa": "2026/0001",
            "status": status,
            "criado_por": self.operador,
            "data_baixa": timezone.localdate(),
            "aprovado_por": self.gestor if status == constants.ACEITA else None,
            "data_aprovacao": timezone.now() if status == constants.ACEITA else None,
        }
        defaults.update(kwargs)
        return BaixaFisicaBemPatrimonial.objects.create(**defaults)

    def vincular_bem_na_baixa(self, baixa, bem):
        return BaixaFisicaBensItem.objects.create(baixa=baixa, bem=bem)


class TestObterBensBaixa(NBBPMTestBase):
    def test_bens_via_itens(self):
        baixa = self.criar_baixa()
        bem1 = self.criar_bem(numero_patrimonial="001.000000002-2")
        bem2 = self.criar_bem(numero_patrimonial="001.000000001-1")

        self.vincular_bem_na_baixa(baixa, bem1)
        self.vincular_bem_na_baixa(baixa, bem2)

        bens = obter_bens_baixa(baixa)
        self.assertEqual(len(bens), 2)
        self.assertEqual(bens[0], bem2)
        self.assertEqual(bens[1], bem1)

    def test_ordenacao_quando_numero_patrimonial_vazio(self):
        baixa = self.criar_baixa()
        bem_sem_num = self.criar_bem(numero_patrimonial="")
        bem_com_num = self.criar_bem(numero_patrimonial="001.000000010-0")

        self.vincular_bem_na_baixa(baixa, bem_sem_num)
        self.vincular_bem_na_baixa(baixa, bem_com_num)

        bens = obter_bens_baixa(baixa)

        self.assertEqual(bens[0], bem_sem_num)
        self.assertEqual(bens[1], bem_com_num)


class TestGeracaoNumeroNBBPM(NBBPMTestBase):
    def test_formato_numero_nbbpm(self):
        baixa = self.criar_baixa()
        numero = gerar_numero_nbbpm(baixa)

        partes = numero.split(".")
        self.assertEqual(len(partes), 3)
        self.assertEqual(partes[0], "287")
        self.assertEqual(len(partes[1]), 7)
        self.assertEqual(len(partes[2]), 4)

    def test_geracao_sequencial_mesmo_ano(self):
        baixa1 = self.criar_baixa()
        baixa2 = self.criar_baixa(numero_processo_baixa="2026/0002")

        n1 = gerar_numero_nbbpm(baixa1)

        baixa1.numero_nbbpm = n1
        baixa1.save(update_fields=["numero_nbbpm"])

        n2 = gerar_numero_nbbpm(baixa2)

        ano = timezone.localdate().year
        self.assertEqual(n1, f"287.0000001.{ano}")
        self.assertEqual(n2, f"287.0000002.{ano}")

    def test_sequencial_reinicia_ao_mudar_ano(self):
        baixa_a = self.criar_baixa(data_baixa=timezone.localdate())
        baixa_b = self.criar_baixa(
            numero_processo_baixa="X/2", data_baixa=timezone.localdate()
        )

        dt_2024 = datetime(
            2024, 12, 31, 23, 59, 59, tzinfo=timezone.get_current_timezone()
        )
        dt_2025 = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.get_current_timezone())

        with patch("django.utils.timezone.localdate", return_value=dt_2024.date()):
            baixa_a.data_baixa = dt_2024.date()
            baixa_a.save(update_fields=["data_baixa"])
            n_2024 = gerar_numero_nbbpm(baixa_a)
            baixa_a.numero_nbbpm = n_2024
            baixa_a.save(update_fields=["numero_nbbpm"])

        self.assertEqual(n_2024, "287.0000001.2024")

        with patch("django.utils.timezone.localdate", return_value=dt_2025.date()):
            baixa_b.data_baixa = dt_2025.date()
            baixa_b.save(update_fields=["data_baixa"])
            n_2025 = gerar_numero_nbbpm(baixa_b)

        self.assertEqual(n_2025, "287.0000001.2025")

    def test_objeto_invalido_dispara_validationerror(self):
        with self.assertRaises(ValidationError):
            gerar_numero_nbbpm(object())


class TestGeracaoPDFNBBPM(NBBPMTestBase):
    def test_gera_pdf_quando_aceita(self):
        baixa = self.criar_baixa(status=constants.ACEITA)
        bem = self.criar_bem()
        self.vincular_bem_na_baixa(baixa, bem)

        buffer = gerar_pdf_nbbpm(baixa, usuario_gerador=self.operador)
        self.assertTrue(buffer.getvalue().startswith(b"%PDF"))
        self.assertGreater(len(buffer.getvalue()), 1000)

    def test_nao_gera_pdf_se_nao_aceita(self):
        baixa = self.criar_baixa(status=constants.AGUARDANDO_ENVIO)
        bem = self.criar_bem()
        self.vincular_bem_na_baixa(baixa, bem)

        with self.assertRaises(ValidationError):
            gerar_pdf_nbbpm(baixa, usuario_gerador=self.operador)

    def test_mantem_numero_nbbpm_se_ja_existir(self):
        baixa = self.criar_baixa(status=constants.ACEITA)
        baixa.numero_nbbpm = "287.0001234.2026"
        baixa.save(update_fields=["numero_nbbpm"])

        bem = self.criar_bem()
        self.vincular_bem_na_baixa(baixa, bem)

        buffer = gerar_pdf_nbbpm(baixa, usuario_gerador=self.operador)
        baixa.refresh_from_db()

        self.assertEqual(baixa.numero_nbbpm, "287.0001234.2026")
        self.assertTrue(buffer.getvalue().startswith(b"%PDF"))

    def test_edge_campos_vazios_nao_quebra(self):
        baixa = self.criar_baixa(status=constants.ACEITA, numero_processo_baixa="")

        bem = self.criar_bem(
            descricao="",
            nome="",
            marca="",
            modelo="",
            numero_processo="",
            valor_unitario=Decimal("0.00"),
            numero_patrimonial="",
        )
        self.vincular_bem_na_baixa(baixa, bem)

        buffer = gerar_pdf_nbbpm(baixa, usuario_gerador=self.operador)
        self.assertTrue(buffer.getvalue().startswith(b"%PDF"))

    def test_http_response_headers(self):
        baixa = self.criar_baixa(status=constants.ACEITA)
        bem = self.criar_bem()
        self.vincular_bem_na_baixa(baixa, bem)

        resp = http_response_nbbpm(baixa, usuario_gerador=self.operador)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("attachment", resp["Content-Disposition"])

        self.assertIn(f"NBBPM_{baixa.numero_nbbpm}.pdf", resp["Content-Disposition"])

    def test_objeto_invalido_gera_validationerror(self):
        """Testa cobertura da linha 89 - objeto inválido para gerar_pdf_nbbpm"""
        with self.assertRaises(ValidationError) as context:
            gerar_pdf_nbbpm(object())
        
        self.assertIn("Objeto inválido para gerar NBBPM", str(context.exception))

    def test_pdf_com_baixa_sem_aprovador(self):
        """Testa cobertura da linha 577 - baixa aceita mas sem aprovado_por"""
        baixa = self.criar_baixa(status=constants.ACEITA, aprovado_por=None)
        bem = self.criar_bem()
        self.vincular_bem_na_baixa(baixa, bem)

        buffer = gerar_pdf_nbbpm(baixa, usuario_gerador=self.operador)
        self.assertTrue(buffer.getvalue().startswith(b"%PDF"))
        self.assertGreater(len(buffer.getvalue()), 1000)
