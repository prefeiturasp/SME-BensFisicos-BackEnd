from io import BytesIO
from decimal import Decimal
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock
import os

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

        defaults = dict(
            numero_patrimonial="001.000000001-1",
            nome="Bem Teste",
            descricao="Descrição do bem",
            valor_unitario=Decimal("100.00"),
            marca="Marca X",
            modelo="Modelo Y",
            numero_processo="2025/0001",
            status="APROVADO",
            unidade_administrativa=ua,
            criado_por=self.operador_a,
        )
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
        if "periodo_final" in kwargs:
            periodo_final = kwargs.pop("periodo_final")
        else:
            n = getattr(self, "_eventual_periodo_counter", 0)
            self._eventual_periodo_counter = n + 1
            periodo_final = timezone.localdate() - timedelta(days=n)
        defaults = dict(
            unidade_administrativa=ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=periodo_final,
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.operador_a,
        )
        defaults.update(kwargs)
        return ConciliacaoUA.objects.create(**defaults)

    def criar_conciliacao_anual(self, ua=None, **kwargs):
        ua = ua or self.ua_a

        ano_ref = timezone.localdate().year - 1
        self.criar_parametro_anual_vigente(ano_ref)

        defaults = dict(
            unidade_administrativa=ua,
            tipo=constants.CONCILIACAO_ANUAL,
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.operador_a,
        )
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

    def test_formatar_moeda_brasileira_com_none(self):
        from inventario.relatorio_conciliacao_pdf import formatar_moeda_brasileira

        resultado = formatar_moeda_brasileira(None)
        self.assertEqual(resultado, "R$ 0,00")

    def test_formatar_moeda_brasileira_com_valor(self):
        from inventario.relatorio_conciliacao_pdf import formatar_moeda_brasileira

        resultado = formatar_moeda_brasileira(Decimal("1234.56"))
        self.assertEqual(resultado, "R$ 1.234,56")

    def test_obter_nome_usuario_com_none(self):
        from inventario.relatorio_conciliacao_pdf import obter_nome_usuario

        resultado = obter_nome_usuario(None)
        self.assertEqual(resultado, "-")

    def test_obter_nome_usuario_com_nome(self):
        from inventario.relatorio_conciliacao_pdf import obter_nome_usuario

        usuario = MagicMock()
        usuario.nome = "João Silva"
        usuario.username = "joao"

        resultado = obter_nome_usuario(usuario)
        self.assertEqual(resultado, "João Silva")

    def test_obter_nome_usuario_sem_nome_usa_username(self):
        from inventario.relatorio_conciliacao_pdf import obter_nome_usuario

        usuario = MagicMock()
        usuario.nome = None
        usuario.username = "joao"

        resultado = obter_nome_usuario(usuario)
        self.assertEqual(resultado, "joao")

    def test_fmt_date_com_none(self):
        from inventario.relatorio_conciliacao_pdf import _fmt_date

        resultado = _fmt_date(None)
        self.assertEqual(resultado, "-")

    def test_fmt_date_com_data(self):
        from inventario.relatorio_conciliacao_pdf import _fmt_date

        data = date(2025, 2, 13)
        resultado = _fmt_date(data)
        self.assertEqual(resultado, "13/02/2025")

    def test_fmt_date_com_string(self):
        from inventario.relatorio_conciliacao_pdf import _fmt_date

        resultado = _fmt_date("2025-02-13")
        self.assertEqual(resultado, "2025-02-13")

    def test_fmt_date_com_excecao(self):
        from inventario.relatorio_conciliacao_pdf import _fmt_date

        class ObjetoComExcecao:
            def strftime(self, fmt):
                raise Exception("Erro")

        obj = ObjetoComExcecao()
        resultado = _fmt_date(obj)
        self.assertEqual(resultado, str(obj))

    def test_quebrar_texto_longo_com_none(self):
        from inventario.relatorio_conciliacao_pdf import _quebrar_texto_longo

        resultado = _quebrar_texto_longo(None)
        self.assertEqual(resultado, "-")

    def test_quebrar_texto_longo_com_texto_curto(self):
        from inventario.relatorio_conciliacao_pdf import _quebrar_texto_longo

        texto = "Texto curto"
        resultado = _quebrar_texto_longo(texto)
        self.assertEqual(resultado, "Texto curto")

    def test_quebrar_texto_longo_com_texto_longo(self):
        from inventario.relatorio_conciliacao_pdf import _quebrar_texto_longo

        texto = "A" * 200
        resultado = _quebrar_texto_longo(texto, max_chars=180)
        self.assertEqual(len(resultado), 183)  # 180 + "..."
        self.assertTrue(resultado.endswith("..."))


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

    def test_gerar_pdf_conciliacao_com_data_geracao(self):
        from inventario.relatorio_conciliacao_pdf import gerar_pdf_conciliacao

        data_geracao = timezone.now()
        buf = gerar_pdf_conciliacao(
            self.conciliacao,
            usuario_gerador=self.operador_a,
            data_geracao=data_geracao,
        )

        self.assertTrue(buf.getvalue().startswith(b"%PDF"))

    def test_gerar_pdf_conciliacao_sem_usuario_gerador(self):
        from inventario.relatorio_conciliacao_pdf import gerar_pdf_conciliacao

        buf = gerar_pdf_conciliacao(self.conciliacao, usuario_gerador=None)
        self.assertTrue(buf.getvalue().startswith(b"%PDF"))

    def test_gerar_pdf_conciliacao_com_data_naive(self):
        from inventario.relatorio_conciliacao_pdf import gerar_pdf_conciliacao

        data_naive = datetime(2025, 2, 13, 10, 30)
        buf = gerar_pdf_conciliacao(
            self.conciliacao,
            usuario_gerador=self.operador_a,
            data_geracao=data_naive,
        )

        self.assertTrue(buf.getvalue().startswith(b"%PDF"))

    def test_gerar_pdf_conciliacao_sem_itens(self):
        from inventario.relatorio_conciliacao_pdf import gerar_pdf_conciliacao

        conciliacao_vazia = self.criar_conciliacao_eventual(ua=self.ua_a)
        buf = gerar_pdf_conciliacao(
            conciliacao_vazia, usuario_gerador=self.operador_a
        )

        raw = buf.getvalue()
        self.assertTrue(raw.startswith(b"%PDF"))
        self.assertLess(len(raw), 5000)

    def test_gerar_pdf_conciliacao_com_item_sem_ocorrencia_outra_situacao(self):
        from inventario.relatorio_conciliacao_pdf import gerar_pdf_conciliacao

        conciliacao = self.criar_conciliacao_eventual(ua=self.ua_a)
        bem = self.criar_bem(ua=self.ua_a, numero_patrimonial="001.000000003-3")

        ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=constants.NAO_ENCONTRADO,
            observacao="",
            divergencia="",
            atualizado_por=self.operador_a,
        )

        buf = gerar_pdf_conciliacao(conciliacao, usuario_gerador=self.operador_a)
        self.assertTrue(buf.getvalue().startswith(b"%PDF"))

    def test_gerar_pdf_conciliacao_com_multiplas_paginas(self):
        from inventario.relatorio_conciliacao_pdf import gerar_pdf_conciliacao

        conciliacao = self.criar_conciliacao_eventual(ua=self.ua_a)

        for i in range(100, 150):
            bem = self.criar_bem(
                ua=self.ua_a, numero_patrimonial=f"001.000000{i:03d}-{i}"
            )
            ItemConciliacao.objects.create(
                conciliacao=conciliacao,
                bem=bem,
                situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
                observacao="",
                divergencia="",
                atualizado_por=self.operador_a,
            )

        buf = gerar_pdf_conciliacao(conciliacao, usuario_gerador=self.operador_a)
        raw = buf.getvalue()

        self.assertTrue(raw.startswith(b"%PDF"))
        # Verifica que tem numeração de páginas (indicando múltiplas páginas)
        self.assertGreater(len(raw), 5000)

    def test_criar_info_geracao_sem_usuario(self):
        from inventario.relatorio_conciliacao_pdf import _criar_info_geracao

        elements = _criar_info_geracao(usuario_gerador=None)
        self.assertGreater(len(elements), 0)

    def test_criar_info_geracao_com_data_geracao(self):
        from inventario.relatorio_conciliacao_pdf import _criar_info_geracao

        data_geracao = timezone.now()
        elements = _criar_info_geracao(
            usuario_gerador=self.operador_a, data_geracao=data_geracao
        )
        self.assertGreater(len(elements), 0)

    def test_criar_rodape_conciliacao_com_fechado_por(self):
        from inventario.relatorio_conciliacao_pdf import _criar_rodape_conciliacao

        conciliacao = self.criar_conciliacao_eventual(
            ua=self.ua_a,
            status=constants.CONCILIACAO_FECHADO,
            fechado_por=self.gestor,
        )

        elements = _criar_rodape_conciliacao(conciliacao, usuario_gerador=self.operador_a)
        self.assertGreater(len(elements), 0)

    def test_criar_rodape_conciliacao_sem_fechado_por(self):
        from inventario.relatorio_conciliacao_pdf import _criar_rodape_conciliacao

        conciliacao = self.criar_conciliacao_eventual(
            ua=self.ua_a, status=constants.CONCILIACAO_FECHADO, fechado_por=None
        )

        elements = _criar_rodape_conciliacao(conciliacao, usuario_gerador=self.operador_a)
        self.assertGreater(len(elements), 0)

    def test_criar_rodape_conciliacao_sem_usuario_gerador(self):
        from inventario.relatorio_conciliacao_pdf import _criar_rodape_conciliacao

        elements = _criar_rodape_conciliacao(
            self.conciliacao, usuario_gerador=None
        )
        self.assertGreater(len(elements), 0)

    def test_carregar_logo_com_fallback(self):
        from inventario.relatorio_conciliacao_pdf import _carregar_logo
        from reportlab.lib.styles import getSampleStyleSheet
        from django.conf import settings

        styles = getSampleStyleSheet()

        with patch("inventario.relatorio_conciliacao_pdf.settings") as mock_settings:
            mock_settings.STATIC_ROOT = None
            mock_settings.STATICFILES_DIRS = []
            resultado = _carregar_logo(styles)
            # Deve retornar o fallback (Paragraph com PMSP)
            self.assertIsNotNone(resultado)

    def test_carregar_logo_com_logo_inexistente(self):
        from inventario.relatorio_conciliacao_pdf import _carregar_logo
        from reportlab.lib.styles import getSampleStyleSheet

        styles = getSampleStyleSheet()

        with patch("inventario.relatorio_conciliacao_pdf.os.path.exists", return_value=False):
            with patch("inventario.relatorio_conciliacao_pdf.settings") as mock_settings:
                mock_settings.STATIC_ROOT = "/fake/path"
                resultado = _carregar_logo(styles)
                # Deve retornar o fallback quando logo não existe
                self.assertIsNotNone(resultado)
