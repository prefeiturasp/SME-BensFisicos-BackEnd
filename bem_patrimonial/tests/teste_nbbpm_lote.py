import base64
import re
import zlib
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario

from bem_patrimonial import constants
from bem_patrimonial.models import (
    BaixaFisicaBemPatrimonial,
    BaixaFisicaBensItem,
    BemPatrimonial,
    NBBPM,
)
from bem_patrimonial.nbbpm_lote import (
    gerar_numero_nbbpm_lote,
    gerar_pdf_nbbpm_lote,
    http_response_nbbpm_lote,
    obter_bens_nbbpm_lote,
    _criar_informacoes_gerais,
    _criar_tabela_bens,
)

# ============================================================================
# HELPERS / SETUP BASE
# ============================================================================


def criar_usuario(username, uo, ua, **kwargs):
    return Usuario.objects.create_user(
        username=username,
        email=f"{username}@test.com",
        password="".join(["senha", "123"]),
        unidade_administrativa=ua,
        unidade_orcamentaria=uo,
        **kwargs,
    )


def criar_bem(ua, criado_por, numero_patrimonial="000.000000001-0", **kwargs):
    return BemPatrimonial.objects.create(
        nome=kwargs.pop("nome", "Notebook Dell"),
        descricao=kwargs.pop("descricao", "Notebook para testes"),
        valor_unitario=kwargs.pop("valor_unitario", Decimal("1000.00")),
        marca=kwargs.pop("marca", "Dell"),
        modelo=kwargs.pop("modelo", "Latitude"),
        numero_processo=kwargs.pop("numero_processo", "PROC-TESTE"),
        numero_patrimonial=numero_patrimonial,
        unidade_administrativa=ua,
        criado_por=criado_por,
        status=kwargs.pop("status", constants.APROVADO),
        **kwargs,
    )


def criar_baixa(ua, criado_por, status=constants.ACEITA, **kwargs):
    return BaixaFisicaBemPatrimonial.objects.create(
        unidade_administrativa_origem=ua,
        numero_processo_baixa=kwargs.pop("numero_processo_baixa", "PROC-BX-001"),
        status=status,
        criado_por=criado_por,
        data_baixa=kwargs.pop("data_baixa", timezone.localdate()),
        **kwargs,
    )


def criar_item(bem, baixa):
    return BaixaFisicaBensItem.objects.create(bem=bem, baixa=baixa)


def criar_nbbpm(baixas, criado_por, **kwargs):
    nbbpm = NBBPM.objects.create(
        numero=kwargs.pop("numero", ""),
        numero_processo_baixa=kwargs.pop("numero_processo_baixa", "6016.2025/0117371-7"),
        data_autorizacao=kwargs.pop("data_autorizacao", timezone.localdate()),
        responsavel=kwargs.pop("responsavel", "Responsavel Teste"),
        numero_processo_destinacao_final=kwargs.pop("numero_processo_destinacao_final", ""),
        criado_por=criado_por,
        **kwargs,
    )
    nbbpm.baixas.set(baixas)
    return nbbpm


class BaseSetup(TestCase):
    def setUp(self):
        self.uo = criar_uo(codigo="100", nome="UO Teste", sigla="UOT")
        self.ua = criar_ua(uo=self.uo, codigo="001", nome="UA Teste", sigla="UAT")

        self.usuario = criar_usuario("usuario_nbbpm_lote", self.uo, self.ua)

        self.bem = criar_bem(self.ua, self.usuario, numero_patrimonial="000.000000001-0")
        self.bem2 = criar_bem(self.ua, self.usuario, numero_patrimonial="000.000000002-0")

        self.baixa = criar_baixa(self.ua, self.usuario)
        criar_item(self.bem, self.baixa)


# ============================================================================
# gerar_numero_nbbpm_lote
# ============================================================================


class GerarNumeroNbbpmLoteTestCase(BaseSetup):
    def test_levanta_erro_se_nao_for_instancia_nbbpm(self):
        with self.assertRaises(ValidationError):
            gerar_numero_nbbpm_lote(self.baixa)

        with self.assertRaises(ValidationError):
            gerar_numero_nbbpm_lote(None)

        with self.assertRaises(ValidationError):
            gerar_numero_nbbpm_lote({"data_autorizacao": timezone.localdate()})

    def test_formato_do_numero_gerado(self):
        nbbpm = criar_nbbpm([self.baixa], self.usuario, data_autorizacao=timezone.localdate())

        numero = gerar_numero_nbbpm_lote(nbbpm)

        ano_esperado = nbbpm.data_autorizacao.year
        self.assertEqual(numero, f"001.0000001/{ano_esperado}")

    def test_sequencial_incrementa_dentro_do_mesmo_ano(self):
        data = timezone.localdate()

        nbbpm1 = criar_nbbpm([self.baixa], self.usuario, data_autorizacao=data)
        nbbpm1.numero = gerar_numero_nbbpm_lote(nbbpm1)
        nbbpm1.save(update_fields=["numero"])

        baixa2 = criar_baixa(self.ua, self.usuario, numero_processo_baixa="PROC-BX-002")
        criar_item(self.bem2, baixa2)
        nbbpm2 = criar_nbbpm([baixa2], self.usuario, data_autorizacao=data)

        numero2 = gerar_numero_nbbpm_lote(nbbpm2)

        self.assertEqual(numero2, f"001.0000002/{data.year}")

    def test_sequencial_reinicia_em_outro_ano(self):
        data_ano_atual = timezone.localdate()
        data_ano_anterior = data_ano_atual.replace(year=data_ano_atual.year - 1)

        nbbpm_antigo = criar_nbbpm(
            [self.baixa], self.usuario, data_autorizacao=data_ano_anterior
        )
        nbbpm_antigo.numero = gerar_numero_nbbpm_lote(nbbpm_antigo)
        nbbpm_antigo.save(update_fields=["numero"])

        baixa2 = criar_baixa(self.ua, self.usuario, numero_processo_baixa="PROC-BX-002")
        criar_item(self.bem2, baixa2)
        nbbpm_novo = criar_nbbpm([baixa2], self.usuario, data_autorizacao=data_ano_atual)

        numero_novo = gerar_numero_nbbpm_lote(nbbpm_novo)

        self.assertEqual(
            numero_novo, f"001.0000001/{data_ano_atual.year}"
        )

    def test_usa_codigo_da_unidade_administrativa_das_baixas_vinculadas(self):
        uo2 = criar_uo(codigo="287", nome="UO Dois", sigla="UOD")
        ua2 = criar_ua(uo=uo2, codigo="002", nome="UA Dois", sigla="UAD")
        usuario2 = criar_usuario("usuario_uo2", uo2, ua2)
        bem_uo2 = criar_bem(ua2, usuario2, numero_patrimonial="000.000000009-0")
        baixa_uo2 = criar_baixa(ua2, usuario2, numero_processo_baixa="PROC-UO2")
        criar_item(bem_uo2, baixa_uo2)

        nbbpm = criar_nbbpm([baixa_uo2], usuario2, data_autorizacao=timezone.localdate())

        numero = gerar_numero_nbbpm_lote(nbbpm)

        self.assertTrue(numero.startswith("001."))


# ============================================================================
# obter_bens_nbbpm_lote
# ============================================================================


class ObterBensNbbpmLoteTestCase(BaseSetup):
    def test_retorna_lista_vazia_quando_nao_ha_baixas_vinculadas(self):
        nbbpm = NBBPM.objects.create(
            numero_processo_baixa="PROC-VAZIO",
            data_autorizacao=timezone.localdate(),
            responsavel="Responsável Teste",
            criado_por=self.usuario,
        )

        self.assertEqual(obter_bens_nbbpm_lote(nbbpm), [])

    def test_retorna_bens_ordenados_por_numero_patrimonial(self):
        criar_item(self.bem2, self.baixa)
        nbbpm = criar_nbbpm([self.baixa], self.usuario)

        bens = obter_bens_nbbpm_lote(nbbpm)

        self.assertEqual(
            [b.numero_patrimonial for b in bens],
            ["000.000000001-0", "000.000000002-0"],
        )

    def test_agrega_bens_de_multiplas_baixas(self):
        baixa2 = criar_baixa(self.ua, self.usuario, numero_processo_baixa="PROC-BX-002")
        criar_item(self.bem2, baixa2)

        nbbpm = criar_nbbpm([self.baixa, baixa2], self.usuario)

        bens = obter_bens_nbbpm_lote(nbbpm)

        self.assertEqual(len(bens), 2)
        self.assertCountEqual(
            [b.id for b in bens], [self.bem.id, self.bem2.id]
        )


# ============================================================================
# _criar_informacoes_gerais / _criar_tabela_bens (montagem dos elementos do PDF)
# ============================================================================


class CriarInformacoesGeraisTestCase(BaseSetup):
    def _textos_da_tabela(self, table):
        textos = []
        for linha in table._cellvalues:
            linha_textos = []
            for celula in linha:
                if hasattr(celula, "text"):
                    linha_textos.append(celula.text)
                else:
                    linha_textos.append(celula)
            textos.append(linha_textos)
        return textos

    def test_inclui_dados_fixos_da_sme(self):
        nbbpm = criar_nbbpm([self.baixa], self.usuario)

        [tabela] = _criar_informacoes_gerais(nbbpm)
        textos = self._textos_da_tabela(tabela)

        self.assertIn("SME", textos[1])
        self.assertIn("SECRETARIA MUNICIPAL DE EDUCAÇÃO", textos[1])
        self.assertIn("16", textos[1])

    def test_inclui_dados_da_unidade_orcamentaria(self):
        nbbpm = criar_nbbpm([self.baixa], self.usuario)

        [tabela] = _criar_informacoes_gerais(nbbpm)
        textos = self._textos_da_tabela(tabela)

        self.assertIn(self.uo.sigla.upper(), textos[3])
        self.assertIn(self.uo.codigo, textos[3])

    def test_inclui_dados_do_processo_autorizacao_e_responsavel(self):
        nbbpm = criar_nbbpm(
            [self.baixa],
            self.usuario,
            numero_processo_baixa="6016.2025/0117371-7",
            responsavel="Responsavel Teste",
        )

        [tabela] = _criar_informacoes_gerais(nbbpm)
        textos = self._textos_da_tabela(tabela)

        self.assertIn("6016.2025/0117371-7", textos[5])
        self.assertIn("RESPONSAVEL TESTE", textos[5])

    def test_destinacao_final_na_mesma_linha_quando_ausente(self):
        nbbpm = criar_nbbpm(
            [self.baixa], self.usuario, numero_processo_destinacao_final=""
        )

        [tabela] = _criar_informacoes_gerais(nbbpm)
        textos = self._textos_da_tabela(tabela)

        self.assertEqual(len(tabela._cellvalues), 6)
        self.assertEqual(len(textos[5]), 4)
        self.assertIn("-", textos[5])

    def test_destinacao_final_na_mesma_linha_quando_informado(self):
        nbbpm = criar_nbbpm(
            [self.baixa],
            self.usuario,
            numero_processo_destinacao_final="6016.2025/9999999-9",
        )

        [tabela] = _criar_informacoes_gerais(nbbpm)
        textos = self._textos_da_tabela(tabela)

        self.assertEqual(len(tabela._cellvalues), 6)
        self.assertEqual(len(textos[4]), 4)
        self.assertEqual(len(textos[5]), 4)
        self.assertIn("6016.2025/9999999-9", textos[5])


class CriarTabelaBensTestCase(BaseSetup):
    def _textos_da_tabela(self, table):
        textos = []
        for linha in table._cellvalues:
            linha_textos = []
            for celula in linha:
                if hasattr(celula, "text"):
                    linha_textos.append(celula.text)
                else:
                    linha_textos.append(celula)
            textos.append(linha_textos)
        return textos

    def test_bem_isolado_nao_preenche_ate(self):
        nbbpm = criar_nbbpm([self.baixa], self.usuario)

        [tabela] = _criar_tabela_bens(nbbpm)
        textos = self._textos_da_tabela(tabela)

        linha_bem = textos[2]
        self.assertEqual(linha_bem[0], "000.000000001-0")
        self.assertEqual(linha_bem[1], "")

    def test_sequencia_agrupada_preserva_quantidade_e_valor_total(self):
        criar_item(self.bem2, self.baixa)
        bem3 = criar_bem(self.ua, self.usuario, numero_patrimonial="000.000000003-7")
        criar_item(bem3, self.baixa)
        nbbpm = criar_nbbpm([self.baixa], self.usuario)

        [tabela] = _criar_tabela_bens(nbbpm)
        textos = self._textos_da_tabela(tabela)

        self.assertEqual(len(textos), 4)
        self.assertEqual(textos[2][0:4], ["000.000000001-0", "000.000000003-7", "NOTEBOOK DELL", "3"])
        self.assertIn("1.000,00", textos[2][4])
        self.assertIn("3.000,00", textos[2][5])
        self.assertIn("3", textos[-1][3])
        self.assertIn("3.000,00", textos[-1][5])
        nbbpm.numero = gerar_numero_nbbpm_lote(nbbpm)
        nbbpm.save(update_fields=["numero"])
        self.assertTrue(gerar_pdf_nbbpm_lote(nbbpm).getvalue().startswith(b"%PDF"))

    def test_lacuna_separa_intervalos_e_bem_isolado(self):
        criar_item(self.bem2, self.baixa)
        for numero in ("000.000000004-4", "000.000000005-5", "000.000000008-8"):
            criar_item(criar_bem(self.ua, self.usuario, numero_patrimonial=numero), self.baixa)
        nbbpm = criar_nbbpm([self.baixa], self.usuario)

        [tabela] = _criar_tabela_bens(nbbpm)
        textos = self._textos_da_tabela(tabela)

        self.assertEqual([(linha[0], linha[1], linha[3]) for linha in textos[2:-1]], [
            ("000.000000001-0", "000.000000002-0", "2"),
            ("000.000000004-4", "000.000000005-5", "2"),
            ("000.000000008-8", "", "1"),
        ])
        self.assertIn("5", textos[-1][3])
        self.assertIn("5.000,00", textos[-1][5])

    def test_valor_diferente_nao_agrupa_bens_consecutivos(self):
        self.bem2.valor_unitario = Decimal("500.00")
        self.bem2.save(update_fields=["valor_unitario"])
        criar_item(self.bem2, self.baixa)
        nbbpm = criar_nbbpm([self.baixa], self.usuario)

        [tabela] = _criar_tabela_bens(nbbpm)
        textos = self._textos_da_tabela(tabela)

        self.assertEqual(len(textos[2:-1]), 2)
        self.assertEqual([linha[1] for linha in textos[2:-1]], ["", ""])
        self.assertIn("1.500,00", textos[-1][5])

    def test_discriminacao_usa_nome_do_bem_em_maiusculo(self):
        nbbpm = criar_nbbpm([self.baixa], self.usuario)

        [tabela] = _criar_tabela_bens(nbbpm)
        textos = self._textos_da_tabela(tabela)

        self.assertEqual(textos[2][2], "NOTEBOOK DELL")

    def test_valor_unitario_e_total_sao_iguais_por_item(self):
        nbbpm = criar_nbbpm([self.baixa], self.usuario)

        [tabela] = _criar_tabela_bens(nbbpm)
        textos = self._textos_da_tabela(tabela)

        self.assertEqual(textos[2][4], textos[2][5])
        self.assertIn("1.000,00", textos[2][4])

    def test_total_geral_soma_valores_e_conta_itens(self):
        criar_item(self.bem2, self.baixa)
        nbbpm = criar_nbbpm([self.baixa], self.usuario)

        [tabela] = _criar_tabela_bens(nbbpm)
        textos = self._textos_da_tabela(tabela)

        linha_total = textos[-1]
        self.assertIn("TOTAL GERAL", linha_total[2])
        self.assertIn("2", linha_total[3])
        self.assertIn("2.000,00", linha_total[5])

    def test_retorna_mensagem_quando_nao_ha_bens(self):
        nbbpm = NBBPM.objects.create(
            numero_processo_baixa="PROC-VAZIO",
            data_autorizacao=timezone.localdate(),
            responsavel="Responsável Teste",
            criado_por=self.usuario,
        )

        [elemento] = _criar_tabela_bens(nbbpm)

        self.assertIn("Nenhum bem vinculado", elemento.text)


# ============================================================================
# gerar_pdf_nbbpm_lote
# ============================================================================


class GerarPdfNbbpmLoteTestCase(BaseSetup):
    def test_levanta_erro_se_nao_for_instancia_nbbpm(self):
        with self.assertRaises(ValidationError):
            gerar_pdf_nbbpm_lote(self.baixa)

        with self.assertRaises(ValidationError):
            gerar_pdf_nbbpm_lote(None)

    def test_levanta_erro_se_numero_ainda_nao_foi_gerado(self):
        nbbpm = criar_nbbpm([self.baixa], self.usuario, numero="")

        with self.assertRaises(ValidationError):
            gerar_pdf_nbbpm_lote(nbbpm)

    def test_gera_pdf_valido_com_bens(self):
        nbbpm = criar_nbbpm([self.baixa], self.usuario)
        nbbpm.numero = gerar_numero_nbbpm_lote(nbbpm)
        nbbpm.save(update_fields=["numero"])

        buffer = gerar_pdf_nbbpm_lote(nbbpm, usuario_gerador=self.usuario)

        self.assertIsInstance(buffer, BytesIO)
        conteudo = buffer.getvalue()
        self.assertTrue(conteudo.startswith(b"%PDF"))
        self.assertGreater(len(conteudo), 0)

    def test_gera_pdf_valido_sem_bens_vinculados(self):
        baixa_sem_itens = criar_baixa(
            self.ua, self.usuario, numero_processo_baixa="PROC-SEM-ITENS"
        )
        nbbpm = criar_nbbpm([baixa_sem_itens], self.usuario)
        nbbpm.numero = gerar_numero_nbbpm_lote(nbbpm)
        nbbpm.save(update_fields=["numero"])

        buffer = gerar_pdf_nbbpm_lote(nbbpm)

        self.assertTrue(buffer.getvalue().startswith(b"%PDF"))

    def test_gera_pdf_valido_com_multiplas_baixas_e_bens(self):
        baixa2 = criar_baixa(self.ua, self.usuario, numero_processo_baixa="PROC-BX-002")
        criar_item(self.bem2, baixa2)

        nbbpm = criar_nbbpm([self.baixa, baixa2], self.usuario)
        nbbpm.numero = gerar_numero_nbbpm_lote(nbbpm)
        nbbpm.save(update_fields=["numero"])

        buffer = gerar_pdf_nbbpm_lote(nbbpm)

        self.assertTrue(buffer.getvalue().startswith(b"%PDF"))

    def test_gera_pdf_valido_com_processo_de_destinacao_final(self):
        nbbpm = criar_nbbpm(
            [self.baixa],
            self.usuario,
            numero_processo_destinacao_final="6016.2025/9999999-9",
        )
        nbbpm.numero = gerar_numero_nbbpm_lote(nbbpm)
        nbbpm.save(update_fields=["numero"])

        buffer = gerar_pdf_nbbpm_lote(nbbpm)

        self.assertTrue(buffer.getvalue().startswith(b"%PDF"))


# ============================================================================
# http_response_nbbpm_lote
# ============================================================================


class HttpResponseNbbpmLoteTestCase(BaseSetup):
    @patch("bem_patrimonial.nbbpm_lote.gerar_pdf_nbbpm_lote")
    def test_retorna_response_pdf_com_nome_de_arquivo_correto(self, mock_gerar_pdf):
        mock_gerar_pdf.return_value = BytesIO(b"%PDF-1.4 conteudo falso")

        nbbpm = criar_nbbpm([self.baixa], self.usuario, numero="001.0000001/2026")

        response = http_response_nbbpm_lote(nbbpm, usuario_gerador=self.usuario)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(
            response["Content-Disposition"],
            'attachment; filename="NBBPM_001.0000001/2026.pdf"',
        )
        self.assertEqual(response.content, b"%PDF-1.4 conteudo falso")
        mock_gerar_pdf.assert_called_once_with(nbbpm, usuario_gerador=self.usuario)

    def test_integra_com_gerar_pdf_nbbpm_lote_real(self):
        nbbpm = criar_nbbpm([self.baixa], self.usuario)
        nbbpm.numero = gerar_numero_nbbpm_lote(nbbpm)
        nbbpm.save(update_fields=["numero"])

        response = http_response_nbbpm_lote(nbbpm)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))


# ============================================================================
# Novo layout: cabeçalho, info 4 colunas, larguras padrão e assinaturas
# ============================================================================


def extrair_textos_por_pagina(pdf_bytes):
    """Extrai texto de cada página sem dependência externa."""
    paginas = []
    for match in re.finditer(br"stream(.*?)endstream", pdf_bytes, re.S):
        bruto = match.group(1).strip()
        if bruto.endswith(b"~>"):
            bruto = bruto[:-2].strip()
        try:
            decodificado = base64.a85decode(bruto, adobe=False)
            pagina = zlib.decompress(decodificado)
        except Exception:
            continue
        if b"BT" in pagina:
            paginas.append(pagina.decode("latin-1"))
    return paginas


def criar_nbbpm_com_numero(baixas, usuario, **kwargs):
    nbbpm = criar_nbbpm(baixas, usuario, **kwargs)
    nbbpm.numero = gerar_numero_nbbpm_lote(nbbpm)
    nbbpm.save(update_fields=["numero"])
    return nbbpm


class NovoLayoutNbbpmLoteTestCase(BaseSetup):
    def test_info_quatro_colunas_responsavel_maior(self):
        nbbpm = criar_nbbpm(
            [self.baixa],
            self.usuario,
            numero_processo_baixa="6016.2025/0117371-7",
            responsavel="Nome Completo Longo Para Teste",
            numero_processo_destinacao_final="6016.2025/9999999-9",
        )

        [tabela] = _criar_informacoes_gerais(nbbpm)

        self.assertEqual(len(tabela._argW), 4)
        larguras = [float(w) for w in tabela._argW]
        self.assertGreater(larguras[2], larguras[0])
        self.assertGreater(larguras[2], larguras[1])
        self.assertGreater(larguras[2], larguras[3])

    def test_info_e_bens_mesma_largura_total(self):
        from reportlab.lib.units import cm as cm_unit

        nbbpm = criar_nbbpm([self.baixa], self.usuario)

        [info] = _criar_informacoes_gerais(nbbpm)
        [bens] = _criar_tabela_bens(nbbpm)

        total_info = sum(float(w) for w in info._argW) / cm_unit
        total_bens = sum(float(w) for w in bens._argW) / cm_unit

        self.assertAlmostEqual(total_info, 18.0, places=1)
        self.assertAlmostEqual(total_bens, 18.0, places=1)

    def test_cabecalho_data_unica_mesclada_e_dupla_compativel(self):
        from bem_patrimonial.documentos_pdf_utils import criar_cabecalho_registro_documento

        [unica] = criar_cabecalho_registro_documento(
            titulo_documento="DOC",
            titulo_registro="REGISTRO",
            label_data_1="DATA",
            label_data_2="",
            label_numero="NÚMERO",
            valor_data_1="10/10/2025",
            valor_data_2="",
            valor_numero="001.0000001/2025",
        )
        registro_unica = unica._cellvalues[0][1]
        self.assertEqual(len(registro_unica._cellvalues), 3)

        [dupla] = criar_cabecalho_registro_documento(
            titulo_documento="DOC",
            titulo_registro="REGISTRO",
            label_data_1="BAIXA",
            label_data_2="APROVAÇÃO",
            label_numero="NÚMERO",
            valor_data_1="10/10/2025",
            valor_data_2="11/10/2025",
            valor_numero="001.0000001/2025",
        )
        registro_dupla = dupla._cellvalues[0][1]
        self.assertEqual(len(registro_dupla._cellvalues), 4)

    def test_rodape_final_tem_assinaturas_com_altura_manual(self):
        from bem_patrimonial.nbbpm_lote import _criar_rodape_nbbpm

        nbbpm = criar_nbbpm([self.baixa], self.usuario)
        [tabela] = _criar_rodape_nbbpm(nbbpm)

        self.assertEqual(len(tabela._argW), 2)
        alturas = [float(h) for h in tabela._argH]
        self.assertEqual(len(alturas), 3)
        self.assertAlmostEqual(alturas[1], alturas[2])

    def _criar_usuario_com_rf(self, username, rf):
        usuario = criar_usuario(username, self.uo, self.ua)
        usuario.rf = rf
        usuario.save(update_fields=["rf"])
        return usuario

    def test_gerado_por_exibe_rf_em_pdf_de_uma_pagina(self):
        usuario = self._criar_usuario_com_rf("gerador_rf1", "F123456")
        nbbpm = criar_nbbpm_com_numero([self.baixa], usuario)

        buffer = gerar_pdf_nbbpm_lote(nbbpm, usuario_gerador=usuario)
        paginas = extrair_textos_por_pagina(buffer.getvalue())

        self.assertEqual(len(paginas), 1)
        self.assertIn("Gerado por F123456", paginas[0])
        self.assertIn("CONTADOR", paginas[0])
        self.assertIn("TITULAR", paginas[0])
        self.assertIn("gina", paginas[0])

    def test_assinaturas_so_na_ultima_pagina_com_tres_paginas(self):
        usuario = self._criar_usuario_com_rf("gerador_rf3", "F654321")
        for idx in range(100, 190):
            bem = criar_bem(
                self.ua,
                usuario,
                numero_patrimonial=f"000.{idx:09d}-0",
                nome=f"Bem teste numero {idx} com descricao longa para ocupar espaco",
            )
            criar_item(bem, self.baixa)
        nbbpm = criar_nbbpm_com_numero([self.baixa], usuario)

        buffer = gerar_pdf_nbbpm_lote(nbbpm, usuario_gerador=usuario)
        paginas = extrair_textos_por_pagina(buffer.getvalue())

        self.assertGreaterEqual(len(paginas), 3)
        for texto in paginas:
            self.assertIn("Gerado por F654321", texto)
            self.assertIn("gina", texto)
        for texto in paginas[:-1]:
            self.assertNotIn("CONTADOR", texto)
            self.assertNotIn("TITULAR", texto)
        self.assertIn("CONTADOR", paginas[-1])
        self.assertIn("TITULAR", paginas[-1])

    def test_modelo_antigo_ainda_gera_sem_erro(self):
        from bem_patrimonial.nbbpm import gerar_pdf_nbbpm

        bem = criar_bem(self.ua, self.usuario, numero_patrimonial="000.000000099-0")
        criar_item(bem, self.baixa)
        self.baixa.status = constants.ACEITA
        self.baixa.save(update_fields=["status"])

        buffer = gerar_pdf_nbbpm(self.baixa, usuario_gerador=self.usuario)

        self.assertTrue(buffer.getvalue().startswith(b"%PDF"))

    def test_api_pdf_retorna_200_com_rf_do_usuario(self):
        from usuario.constants import GRUPO_GESTOR_PATRIMONIO

        grupo, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        gestor = self._criar_usuario_com_rf("gestor_api_rf", "F777888")
        gestor.groups.add(grupo)
        nbbpm = criar_nbbpm_com_numero([self.baixa], gestor)

        client = APIClient()
        client.force_authenticate(user=gestor)
        resposta = client.get(f"/api/nbbpm/{nbbpm.id}/pdf/")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta["Content-Type"], "application/pdf")
        paginas = extrair_textos_por_pagina(resposta.content)
        self.assertTrue(paginas)
        self.assertIn("Gerado por F777888", paginas[0])


class ProcessoUnicoNBBPMTestCase(BaseSetup):
    """Serviço de processo único: mesma regra usada por Admin e API."""

    def test_normalizar_e_processos_de_strings_e_objetos(self):
        from bem_patrimonial.services.nbbpm_numero import (
            normalizar_processo,
            processos_normalizados_de_baixas,
        )

        self.assertEqual(normalizar_processo(None), "")
        self.assertEqual(normalizar_processo("  P1  "), "P1")
        self.assertEqual(processos_normalizados_de_baixas(["  P1 ", "P1"]), {"P1"})
        self.assertEqual(processos_normalizados_de_baixas([self.baixa]), {"PROC-BX-001"})

    def test_obter_processo_unico_ok_divergente_e_vazio(self):
        from bem_patrimonial.services.nbbpm_numero import obter_processo_unico_baixas

        self.assertEqual(obter_processo_unico_baixas([self.baixa]), "PROC-BX-001")
        self.assertEqual(obter_processo_unico_baixas([]), "")
        outra = criar_baixa(self.ua, self.usuario, numero_processo_baixa="OUTRO")
        with self.assertRaises(ValidationError) as ctx:
            obter_processo_unico_baixas([self.baixa, outra])
        self.assertIn("divergentes", str(ctx.exception))

    def test_validar_payload_ok_strip_e_divergente(self):
        from bem_patrimonial.services.nbbpm_numero import validar_processo_payload_baixas

        self.assertEqual(
            validar_processo_payload_baixas([self.baixa], "  PROC-BX-001  "),
            "PROC-BX-001",
        )
        with self.assertRaises(ValidationError) as ctx:
            validar_processo_payload_baixas([self.baixa], "DIFERENTE")
        self.assertIn("diverge", str(ctx.exception))

    def test_criar_nbbpm_com_retry_bloqueia_processo_divergente(self):
        from bem_patrimonial.services.nbbpm_numero import criar_nbbpm_com_retry

        outra = criar_baixa(self.ua, self.usuario, numero_processo_baixa="OUTRO")
        with self.assertRaises(ValidationError) as ctx:
            criar_nbbpm_com_retry(
                baixas=[self.baixa, outra],
                numero_processo_baixa="PROC-BX-001",
                data_autorizacao=timezone.localdate(),
                responsavel="G",
                criado_por=self.usuario,
            )
        self.assertIn("divergentes", str(ctx.exception))
        with self.assertRaises(ValidationError) as ctx2:
            criar_nbbpm_com_retry(
                baixas=[self.baixa],
                numero_processo_baixa="DIFERENTE",
                data_autorizacao=timezone.localdate(),
                responsavel="G",
                criado_por=self.usuario,
            )
        self.assertIn("diverge", str(ctx2.exception))
