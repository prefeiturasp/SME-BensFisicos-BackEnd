from io import BytesIO
from decimal import Decimal
from datetime import date
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import Group
from django.utils import timezone

from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO

from bem_patrimonial.models import BemPatrimonial

from inventario.models import (
    ConciliacaoUA,
    ItemConciliacao,
    OcorrenciaConciliacao,
    ParametroConciliacaoAnual,
)
from inventario import constants


class ConciliacaoPDFTestBase(TestCase):
    def setUp(self):
        self.client = Client()

        self.grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.grupo_operador, _ = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )

        self.ua_a = criar_ua(
            codigo="01.16.10.379",
            sigla="UA_A",
            nome="Unidade A",
            status=UnidadeAdministrativa.ATIVA,
        )
        self.ua_b = criar_ua(
            uo=self.ua_a.unidade_orcamentaria,
            codigo="01.16.10.408",
            sigla="UA_B",
            nome="Unidade B",
            status=UnidadeAdministrativa.ATIVA,
        )

        self.operador_a = Usuario.objects.create_user(
            username="operador_a",
            nome="Operador A",
            rf="1111111",
            email="operador_a@exemplo.com",
            password="senha123",
            unidade_administrativa=self.ua_a,
            unidade_orcamentaria=self.ua_a.unidade_orcamentaria,
        )
        self.operador_a.groups.add(self.grupo_operador)

        self.operador_b = Usuario.objects.create_user(
            username="operador_b",
            nome="Operador B",
            rf="2222222",
            email="operador_b@exemplo.com",
            password="senha123",
            unidade_administrativa=self.ua_b,
            unidade_orcamentaria=self.ua_b.unidade_orcamentaria,
        )
        self.operador_b.groups.add(self.grupo_operador)

        self.gestor = Usuario.objects.create_user(
            username="gestor",
            nome="Gestor",
            rf="9999999",
            email="gestor@exemplo.com",
            password="senha123",
            unidade_administrativa=self.ua_b,
        )
        self.gestor.groups.add(self.grupo_gestor)

    def criar_bem(self, ua=None, **kwargs):
        ua = ua or self.ua_a

        defaults = {
            "numero_patrimonial": "001.000000001-1",
            "nome": "Bem Teste",
            "descricao": "Descrição do bem",
            "valor_unitario": Decimal("100.00"),
            "marca": "Marca X",
            "modelo": "Modelo Y",
            "numero_processo": "2025/0001",
            "status": "APROVADO",
            "unidade_administrativa": ua,
            "criado_por": self.operador_a,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def criar_parametro_anual_vigente(self, ano_referencia: int):
        """
        Necessário para criar/fechar conciliação ANUAL, senão o clean() bloqueia.
        """
        hoje = timezone.localdate()
        return ParametroConciliacaoAnual.objects.create(
            ano_referencia=ano_referencia,
            periodo_inicial=hoje.replace(month=1, day=1),
            periodo_final=hoje.replace(month=12, day=31),
            ativo=True,
        )

    def criar_conciliacao_eventual(self, ua=None, **kwargs):
        ua = ua or self.ua_a
        defaults = {
            "unidade_administrativa": ua,
            "tipo": constants.CONCILIACAO_EVENTUAL,
            "periodo_final": timezone.localdate(),
            "status": constants.CONCILIACAO_EM_ABERTO,
            "criado_por": self.operador_a,
        }
        defaults.update(kwargs)
        return ConciliacaoUA.objects.create(**defaults)

    def criar_conciliacao_anual(self, ua=None, **kwargs):
        ua = ua or self.ua_a

        ano_ref = timezone.localdate().year - 1
        self.criar_parametro_anual_vigente(ano_ref)

        defaults = {
            "unidade_administrativa": ua,
            "tipo": constants.CONCILIACAO_ANUAL,
            "status": constants.CONCILIACAO_EM_ABERTO,
            "criado_por": self.operador_a,
        }
        defaults.update(kwargs)
        return ConciliacaoUA.objects.create(**defaults)


class TestDownloadConciliacaoPDFView(ConciliacaoPDFTestBase):
    def setUp(self):
        super().setUp()
        self.conciliacao = self.criar_conciliacao_eventual(ua=self.ua_a)
        self.url = reverse(
            "download_conciliacao_pdf", kwargs={"pk": self.conciliacao.pk}
        )

    def test_nao_autenticado_redireciona_login(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.url)

    def test_operador_da_mesma_ua_pode_baixar(self):
        self.client.login(username="operador_a", password="senha123")

        with patch(
            "inventario.views.gerar_pdf_conciliacao",
            return_value=BytesIO(b"%PDF-1.4\n..."),
        ):
            resp = self.client.get(self.url)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("attachment", resp["Content-Disposition"])

    def test_operador_de_outra_ua_recebe_403(self):
        self.client.login(username="operador_b", password="senha123")

        with patch(
            "inventario.views.gerar_pdf_conciliacao",
            return_value=BytesIO(b"%PDF-1.4\n..."),
        ):
            resp = self.client.get(self.url)

        self.assertEqual(resp.status_code, 403)

    def test_gestor_pode_baixar_qualquer_ua(self):
        self.client.login(username="gestor", password="senha123")

        with patch(
            "inventario.views.gerar_pdf_conciliacao",
            return_value=BytesIO(b"%PDF-1.4\n..."),
        ):
            resp = self.client.get(self.url)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_conciliacao_inexistente_retorna_404(self):
        self.client.login(username="gestor", password="senha123")
        url = reverse("download_conciliacao_pdf", kwargs={"pk": 999999})

        with patch(
            "inventario.views.gerar_pdf_conciliacao",
            return_value=BytesIO(b"%PDF-1.4\n..."),
        ):
            resp = self.client.get(url)

        self.assertEqual(resp.status_code, 404)

    def test_filename_tem_numero_e_ua(self):
        self.client.login(username="gestor", password="senha123")

        with patch(
            "inventario.views.gerar_pdf_conciliacao",
            return_value=BytesIO(b"%PDF-1.4\n..."),
        ):
            resp = self.client.get(self.url)

        disp = resp["Content-Disposition"]

        self.assertIn("attachment", disp)
        self.assertIn('filename="', disp)

        self.assertIn("001", disp)

        self.assertIn(f"UA{self.ua_a.codigo}", disp)

        self.assertIn(".pdf", disp)

    def test_pdf_streaming_valido(self):
        self.client.login(username="gestor", password="senha123")

        fake = BytesIO(b"%PDF-1.4\nconteudo\n%%EOF")
        with patch("inventario.views.gerar_pdf_conciliacao", return_value=fake):
            resp = self.client.get(self.url)

        content = b"".join(resp.streaming_content)
        self.assertTrue(content.startswith(b"%PDF"))


class TestHelpersRelatorioConciliacao(TestCase):
    def test_formatar_status_para_header_quando_nao_conciliado(self):
        class Dummy:
            def get_status_display(self):
                return "Fechado pelo Administrador -Não Conciliado"

        from inventario.relatorio_conciliacao_pdf import formatar_status_para_header

        self.assertEqual(formatar_status_para_header(Dummy()), "Não Conciliado")

    def test_formatar_status_para_header_padrao(self):
        class Dummy:
            def get_status_display(self):
                return "Fechado"

        from inventario.relatorio_conciliacao_pdf import formatar_status_para_header

        self.assertEqual(formatar_status_para_header(Dummy()), "Fechado")


class TestGerarPDFConciliacao(ConciliacaoPDFTestBase):
    def setUp(self):
        super().setUp()
        self.conciliacao = self.criar_conciliacao_eventual(ua=self.ua_a)

        bem1 = self.criar_bem(ua=self.ua_a, numero_patrimonial="001.000000001-1")
        bem2 = self.criar_bem(ua=self.ua_a, numero_patrimonial="001.000000002-2")

        ItemConciliacao.objects.create(
            conciliacao=self.conciliacao,
            bem=bem1,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
            observacao="",
            divergencia="",
            atualizado_por=self.operador_a,
        )

        item2 = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao,
            bem=bem2,
            situacao=constants.DIVERGENTE,
            observacao="Obs do item",
            divergencia="Divergência do item",
            atualizado_por=self.operador_a,
        )

        OcorrenciaConciliacao.objects.create(
            item=item2,
            situacao=constants.DIVERGENTE,
            observacao="Obs ocorrência",
            divergencia="Divergência ocorrência",
            registrado_por=self.operador_a,
        )

    def test_gerar_pdf_conciliacao_retorna_pdf(self):
        from inventario.relatorio_conciliacao_pdf import gerar_pdf_conciliacao

        buf = gerar_pdf_conciliacao(self.conciliacao, usuario_gerador=self.operador_a)
        raw = buf.getvalue()

        self.assertTrue(raw.startswith(b"%PDF"))
        self.assertGreater(len(raw), 1000)

    def test_gerar_pdf_conciliacao_sem_logo_nao_quebra(self):
        from inventario.relatorio_conciliacao_pdf import gerar_pdf_conciliacao

        with patch(
            "inventario.relatorio_conciliacao_pdf.Image",
            side_effect=Exception("sem logo"),
        ):
            buf = gerar_pdf_conciliacao(
                self.conciliacao, usuario_gerador=self.operador_a
            )

        self.assertTrue(buf.getvalue().startswith(b"%PDF"))
