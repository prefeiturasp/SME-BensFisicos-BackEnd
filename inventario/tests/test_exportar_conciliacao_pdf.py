from dados_comuns.tests.auth_test_utils import auth_kwargs
from io import BytesIO
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import Group
from django.utils import timezone
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Spacer

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
            **auth_kwargs("senha123"),
            unidade_administrativa=self.ua_a,
            unidade_orcamentaria=self.ua_a.unidade_orcamentaria,
        )
        self.operador_a.groups.add(self.grupo_operador)
        self.operador_a.unidades_administrativas.add(self.ua_a)

        self.operador_b = Usuario.objects.create_user(
            username="operador_b",
            nome="Operador B",
            rf="2222222",
            email="operador_b@exemplo.com",
            **auth_kwargs("senha123"),
            unidade_administrativa=self.ua_b,
            unidade_orcamentaria=self.ua_b.unidade_orcamentaria,
        )
        self.operador_b.groups.add(self.grupo_operador)
        self.operador_b.unidades_administrativas.add(self.ua_b)

        self.gestor = Usuario.objects.create_user(
            username="gestor",
            nome="Gestor",
            rf="9999999",
            email="gestor@exemplo.com",
            **auth_kwargs("senha123"),
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
            "periodo_final": timezone.localdate() - timezone.timedelta(days=1),
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
        self.client.login(username="operador_a", **auth_kwargs("senha123"))

        with patch(
            "inventario.views.gerar_pdf_conciliacao",
            return_value=BytesIO(b"%PDF-1.4\n..."),
        ):
            resp = self.client.get(self.url)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn("attachment", resp["Content-Disposition"])

    def test_operador_de_outra_ua_recebe_403(self):
        self.client.login(username="operador_b", **auth_kwargs("senha123"))

        with patch(
            "inventario.views.gerar_pdf_conciliacao",
            return_value=BytesIO(b"%PDF-1.4\n..."),
        ):
            resp = self.client.get(self.url)

        self.assertEqual(resp.status_code, 403)

    def test_gestor_pode_baixar_qualquer_ua(self):
        self.client.login(username="gestor", **auth_kwargs("senha123"))

        with patch(
            "inventario.views.gerar_pdf_conciliacao",
            return_value=BytesIO(b"%PDF-1.4\n..."),
        ):
            resp = self.client.get(self.url)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

    def test_conciliacao_inexistente_retorna_404(self):
        self.client.login(username="gestor", **auth_kwargs("senha123"))
        url = reverse("download_conciliacao_pdf", kwargs={"pk": 999999})

        with patch(
            "inventario.views.gerar_pdf_conciliacao",
            return_value=BytesIO(b"%PDF-1.4\n..."),
        ):
            resp = self.client.get(url)

        self.assertEqual(resp.status_code, 404)

    def test_filename_tem_numero_e_ua(self):
        self.client.login(username="gestor", **auth_kwargs("senha123"))

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
        self.client.login(username="gestor", **auth_kwargs("senha123"))

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

    def test_info_geracao_exibe_apenas_rf(self):
        ua = criar_ua(
            codigo="01.16.10.501",
            sigla="UA",
            nome="Unidade",
            status=UnidadeAdministrativa.ATIVA,
        )
        usuario = Usuario.objects.create_user(
            username="operador_rf",
            nome="Operador Nome Completo",
            rf="3333333",
            email="operador_rf@exemplo.com",
            **auth_kwargs("senha123"),
            unidade_administrativa=ua,
            unidade_orcamentaria=ua.unidade_orcamentaria,
        )

        from inventario.relatorio_conciliacao_pdf import _criar_info_geracao

        info_paragraph = _criar_info_geracao(usuario)[0]
        info_texto = info_paragraph.getPlainText()

        self.assertIn("Gerado por 3333333 em ", info_texto)
        self.assertNotIn("Operador Nome Completo", info_texto)

    def test_estilos_blocos_itens_usa_fonte_8(self):
        from inventario.relatorio_conciliacao_pdf import _estilos_blocos_itens

        estilos = _estilos_blocos_itens(getSampleStyleSheet())

        self.assertEqual(estilos["txt"].fontSize, 8)
        self.assertEqual(estilos["txt"].leading, 9)
        self.assertEqual(estilos["txt_center"].fontSize, 8)
        self.assertEqual(estilos["txt_center"].leading, 9)
        self.assertEqual(estilos["totalizador_label"].fontName, "Helvetica-Bold")
        self.assertEqual(estilos["totalizador_valor"].fontName, "Helvetica-Bold")
        self.assertEqual(
            estilos["totalizador_geral_label"].fontName, "Helvetica-Bold"
        )
        self.assertEqual(estilos["ocorrencia_badge"].fontName, "Helvetica-Bold")


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

    def test_rodape_e_ocorrencia_exibem_apenas_rf(self):
        from inventario.relatorio_conciliacao_pdf import (
            _criar_rodape_conciliacao,
            _linhas_tabela_item,
            _estilos_blocos_itens,
        )

        self.conciliacao.fechado_por = self.gestor

        rodape_table = _criar_rodape_conciliacao(
            self.conciliacao, usuario_gerador=self.operador_a
        )[0]
        responsavel_exportacao = rodape_table._cellvalues[1][0].getPlainText()
        responsavel_fechamento = rodape_table._cellvalues[1][1].getPlainText()

        self.assertEqual(responsavel_exportacao, "1111111")
        self.assertEqual(responsavel_fechamento, "9999999")
        self.assertNotIn("Operador A", responsavel_exportacao)
        self.assertNotIn("Gestor", responsavel_fechamento)

        item_com_ocorrencia = self.conciliacao.itens.get(situacao=constants.DIVERGENTE)
        estilos = _estilos_blocos_itens(getSampleStyleSheet())
        rows, _ = _linhas_tabela_item(item_com_ocorrencia, estilos)

        self.assertIn(
            "ITEM COM OCORRÊNCIA NESTA CONCILIAÇÃO",
            rows[-1][0].getPlainText(),
        )
        registrado_por = rows[-1][1].getPlainText()

        self.assertEqual(registrado_por, "Registrado por: 1111111")
        self.assertNotIn("Operador A", registrado_por)


class TestGerarPDFConciliacaoCategoriasETotais(ConciliacaoPDFTestBase):
    """Cobertura da reestruturação do relatório nas 5 categorias de situação."""

    def setUp(self):
        super().setUp()
        self.conciliacao = self.criar_conciliacao_eventual(ua=self.ua_a)

        valores = {
            constants.ENCONTRADO_SEM_DIVERGENCIA: Decimal("100.00"),
            constants.ENCONTRADO: Decimal("250.00"),
            constants.NAO_ENCONTRADO: Decimal("310.00"),
            constants.DIVERGENTE: Decimal("420.00"),
            constants.EM_PROCESSO_BAIXA_FISICA: Decimal("530.00"),
            constants.BAIXA_FISICA: Decimal("0.00"),
        }

        self.itens = {}
        for i, (situacao, valor) in enumerate(valores.items(), start=1):
            bem = self.criar_bem(
                ua=self.ua_a,
                numero_patrimonial=f"001.000000{i:03d}-{i}",
                valor_unitario=valor,
            )
            item = ItemConciliacao.objects.create(
                conciliacao=self.conciliacao,
                bem=bem,
                situacao=situacao,
                observacao="" if situacao != constants.DIVERGENTE else "Obs do item",
                divergencia=(
                    "Divergência do item"
                    if situacao == constants.DIVERGENTE
                    else ""
                ),
                atualizado_por=self.operador_a,
            )
            self.itens[situacao] = item

        OcorrenciaConciliacao.objects.create(
            item=self.itens[constants.DIVERGENTE],
            situacao=constants.DIVERGENTE,
            observacao="Obs ocorrência",
            divergencia="Divergência ocorrência",
            registrado_por=self.operador_a,
        )

    def _coletar_texto_blocos(self, conciliacao=None):
        """Recupera o texto dos elementos (blocos) que compõem o corpo do PDF."""
        conciliacao = conciliacao or self.conciliacao
        from inventario.relatorio_conciliacao_pdf import _criar_blocos_itens_conciliacao
        from reportlab.platypus import KeepTogether, Paragraph, Table

        textos = []

        def percorrer(flowables):
            for el in flowables:
                if isinstance(el, Paragraph):
                    textos.append(el.getPlainText())
                elif isinstance(el, KeepTogether):
                    percorrer(el._content)
                elif isinstance(el, Table):
                    for row in el._cellvalues:
                        for cell in row:
                            percorrer([cell])

        percorrer(_criar_blocos_itens_conciliacao(conciliacao))
        return "\n".join(t for t in textos if t)

    def test_pdf_agrupa_por_categorias_de_situacao(self):
        texto = self._coletar_texto_blocos()

        self.assertIn("Encontrados / Sem divergência (2)", texto)
        self.assertIn("Não encontrados (1)", texto)
        self.assertIn("Divergentes (1)", texto)
        self.assertIn("Em processo de baixa (1)", texto)
        self.assertIn("Baixa Física (1)", texto)

        self.assertNotIn("Itens encontrados sem divergência", texto)
        self.assertNotIn("Itens com ocorrência / divergência", texto)

    def test_pdf_linhas_valor_total_por_categoria_e_geral(self):
        texto = self._coletar_texto_blocos()

        totais = [
            ("Encontrados", "2 itens", "R$ 350,00"),
            ("Não encontrados", "1 item", "R$ 310,00"),
            ("Divergentes", "1 item", "R$ 420,00"),
            ("Em processo de baixa", "1 item", "R$ 530,00"),
            ("Baixa Física", "1 item", "R$ 0,00"),
        ]

        posicao_anterior = -1
        for titulo, quantidade, valor in totais:
            posicao_titulo = texto.index(titulo)
            self.assertGreater(posicao_titulo, posicao_anterior)

            posicao_label = texto.index("Valor total da categoria", posicao_titulo)
            posicao_quantidade = texto.index(quantidade, posicao_label)
            posicao_valor = texto.index(valor, posicao_quantidade)
            self.assertLess(posicao_valor, posicao_label + 200)

            posicao_anterior = posicao_valor

        posicao_geral = texto.index("Valor total geral", posicao_anterior)
        self.assertGreater(posicao_geral, posicao_anterior)
        posicao_quantidade_geral = texto.index("6 itens", posicao_geral)
        posicao_valor_geral = texto.index("R$ 1.610,00", posicao_quantidade_geral)
        self.assertEqual(posicao_valor_geral, texto.rfind("R$ 1.610,00"))

    def test_titulo_categoria_agrupado_com_primeiro_item(self):
        from inventario.relatorio_conciliacao_pdf import _criar_blocos_itens_conciliacao
        from reportlab.platypus import KeepTogether, Table

        elements = _criar_blocos_itens_conciliacao(self.conciliacao)

        primeiro = elements[0]
        self.assertIsInstance(primeiro, KeepTogether)
        conteudo = primeiro._content
        self.assertIsInstance(conteudo[0], Table)
        texto_titulo = conteudo[0]._cellvalues[0][0].getPlainText()
        self.assertIn("Encontrados", texto_titulo)
        self.assertIsInstance(conteudo[1], Spacer)

    def test_totalizador_categoria_tem_tres_celulas_com_grade(self):
        from inventario.relatorio_conciliacao_pdf import _criar_blocos_itens_conciliacao
        from reportlab.platypus import KeepTogether, Table

        elements = _criar_blocos_itens_conciliacao(self.conciliacao)

        totalizador = elements[1]._content[-1]
        self.assertIsInstance(totalizador, Table)
        celulas = totalizador._cellvalues[0]
        self.assertEqual(celulas[0].getPlainText(), "Valor total da categoria")
        self.assertEqual(celulas[1].getPlainText(), "2 itens")
        self.assertEqual(celulas[2].getPlainText(), "R$ 350,00")
        self.assertIn(
            "INNERGRID",
            [cmd[0] for cmd in totalizador._linecmds],
        )

    def test_total_geral_ultimo_elemento_com_tres_celulas(self):
        from inventario.relatorio_conciliacao_pdf import _criar_blocos_itens_conciliacao
        from reportlab.platypus import Table

        elements = _criar_blocos_itens_conciliacao(self.conciliacao)

        self.assertIsInstance(elements[-1], Table)
        celulas = elements[-1]._cellvalues[0]
        self.assertEqual(celulas[0].getPlainText(), "Valor total geral")
        self.assertEqual(celulas[1].getPlainText(), "6 itens")
        self.assertEqual(celulas[2].getPlainText(), "R$ 1.610,00")
        self.assertIn(
            "INNERGRID",
            [cmd[0] for cmd in elements[-1]._linecmds],
        )

    def test_espacamentos_entre_categorias_e_apos_titulo(self):
        from inventario.relatorio_conciliacao_pdf import (
            _criar_blocos_itens_conciliacao,
            PDFConfig,
        )
        from reportlab.platypus import Spacer, Table

        elements = _criar_blocos_itens_conciliacao(self.conciliacao)

        espaco_categorias = elements[2]
        self.assertIsInstance(espaco_categorias, Spacer)
        self.assertAlmostEqual(
            espaco_categorias.height,
            PDFConfig.ESPACO_ENTRE_CATEGORIAS,
            places=2,
        )

        self.assertIsInstance(elements[-2], Spacer)
        self.assertAlmostEqual(
            elements[-2].height, PDFConfig.ESPACO_ENTRE_CATEGORIAS, places=2
        )
        self.assertIsInstance(elements[-1], Table)

        conteudo = elements[0]._content
        self.assertIsInstance(conteudo[1], Spacer)
        self.assertAlmostEqual(
            conteudo[1].height,
            PDFConfig.ESPACO_APOS_TITULO_CATEGORIA,
            places=2,
        )

    def test_conciliacao_sem_itens_exibe_aviso_e_total_geral_zero(self):
        vazia = self.criar_conciliacao_eventual(
            ua=self.ua_a,
            periodo_final=timezone.localdate() - timezone.timedelta(days=2),
        )
        texto = self._coletar_texto_blocos(vazia)

        self.assertIn("Nenhum item encontrado para esta conciliação.", texto)
        self.assertIn("Valor total geral", texto)
        self.assertIn("0 itens", texto)
        self.assertIn("R$ 0,00", texto)

    def test_pdf_multipagina_com_muitos_itens_gera_pdf(self):
        from inventario.relatorio_conciliacao_pdf import gerar_pdf_conciliacao

        conc = self.criar_conciliacao_eventual(
            ua=self.ua_a,
            periodo_final=timezone.localdate() - timezone.timedelta(days=7),
        )
        situacoes = (
            [constants.ENCONTRADO_SEM_DIVERGENCIA] * 30
            + [constants.NAO_ENCONTRADO] * 12
            + [constants.DIVERGENTE] * 8
            + [constants.EM_PROCESSO_BAIXA_FISICA] * 6
            + [constants.BAIXA_FISICA] * 4
        )
        for i, sit in enumerate(situacoes):
            bem = self.criar_bem(
                ua=self.ua_a,
                numero_patrimonial=f"002.{i:09d}-{i}",
                valor_unitario=Decimal("100.00"),
            )
            ItemConciliacao.objects.create(
                conciliacao=conc,
                bem=bem,
                situacao=sit,
                observacao="",
                divergencia="Div" if sit == constants.DIVERGENTE else "",
                atualizado_por=self.operador_a,
            )

        buf = gerar_pdf_conciliacao(conc, usuario_gerador=self.operador_a)
        raw = buf.getvalue()
        self.assertTrue(raw.startswith(b"%PDF"))
        paginas = raw.count(b"/Type /Page") - raw.count(b"/Type /Pages")
        self.assertGreater(paginas, 1)

    def test_pdf_sinaliza_item_com_ocorrencia(self):
        texto = self._coletar_texto_blocos()

        self.assertEqual(
            texto.count("ITEM COM OCORRÊNCIA NESTA CONCILIAÇÃO"), 1
        )
