import csv
from io import StringIO
from unittest.mock import patch

from django.contrib.admin import helpers
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO

from bem_patrimonial import constants
from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.admins.actions.extracao_numeros import (
    _digits_only,
    _coerce_to_new,
    _first_token,
    _last_numericish_token,
    _classify_token,
    _extract,
    simular_extracao_numero,
    aplicar_extracao_numero,
)


User = get_user_model()


class TestDigitsOnly(TestCase):
    """Testes para _digits_only()."""

    def test_remove_nao_numericos(self):
        self.assertEqual(_digits_only("001.050.761.830-0"), "0010507618300")

    def test_remove_pontos_hifens_espacos(self):
        self.assertEqual(_digits_only("001 050 761 830-0"), "0010507618300")

    def test_string_vazia_retorna_vazia(self):
        self.assertEqual(_digits_only(""), "")

    def test_none_retorna_vazia(self):
        self.assertEqual(_digits_only(None), "")

    def test_apenas_letras_retorna_vazia(self):
        self.assertEqual(_digits_only("ABC"), "")

    def test_mantem_apenas_digitos(self):
        self.assertEqual(_digits_only("a1b2c3"), "123")


class TestCoerceToNew(TestCase):
    """Testes para _coerce_to_new()."""

    def test_13_digitos_formata_corretamente(self):
        resultado = _coerce_to_new("0010507618300")
        self.assertEqual(resultado, "001.050761830-0")

    def test_13_digitos_com_formatacao_remove_e_formata(self):
        resultado = _coerce_to_new("001.050.761.830-0")
        self.assertEqual(resultado, "001.050761830-0")

    def test_14_digitos_retorna_none(self):
        self.assertIsNone(_coerce_to_new("00105076183000"))

    def test_12_digitos_retorna_none(self):
        self.assertIsNone(_coerce_to_new("001050761830"))

    def test_string_vazia_retorna_none(self):
        self.assertIsNone(_coerce_to_new(""))

    def test_apenas_letras_retorna_none(self):
        self.assertIsNone(_coerce_to_new("ABC"))


class TestFirstToken(TestCase):
    """Testes para _first_token()."""

    def test_extrai_token_ate_espaco(self):
        token, pos, end = _first_token("001050761830-0 ARMÁRIO")
        self.assertEqual(token, "001050761830-0")
        self.assertEqual(pos, 0)
        self.assertEqual(end, 14)

    def test_extrai_token_ate_barra(self):
        token, pos, end = _first_token("001.050.761.830-3/ mesa")
        self.assertEqual(token, "001.050.761.830-3")
        self.assertEqual(pos, 0)
        self.assertEqual(end, 17)

    def test_remove_barra_final(self):
        token, pos, end = _first_token("001050761830-0/")
        self.assertEqual(token, "001050761830-0")
        self.assertEqual(pos, 0)
        self.assertEqual(end, 14)

    def test_string_vazia_retorna_none(self):
        token, pos, end = _first_token("")
        self.assertIsNone(token)
        self.assertIsNone(pos)
        self.assertIsNone(end)

    def test_apenas_espacos_retorna_none(self):
        token, pos, end = _first_token("   ")
        self.assertIsNone(token)
        self.assertIsNone(pos)
        self.assertIsNone(end)

    def test_sem_separador_retorna_tudo(self):
        token, pos, end = _first_token("001050761830-0")
        self.assertEqual(token, "001050761830-0")
        self.assertEqual(pos, 0)
        self.assertEqual(end, 14)


class TestLastNumericishToken(TestCase):
    """Testes para _last_numericish_token()."""

    def test_extrai_token_numerico_no_fim(self):
        token, start, end = _last_numericish_token("ARMÁRIO 001050761830-0")
        self.assertEqual(token, "001050761830-0")
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)

    def test_aceita_pontos_hifens_espacos_no_token(self):
        token, start, end = _last_numericish_token("Bem 001.050.761.830-0")
        self.assertEqual(token, "001.050.761.830-0")
        self.assertIsNotNone(start)

    def test_rejeita_se_contem_letras(self):
        token, start, end = _last_numericish_token("001050761830-0ABC")
        self.assertIsNone(token)

    def test_string_vazia_retorna_none(self):
        token, start, end = _last_numericish_token("")
        self.assertIsNone(token)

    def test_apenas_letras_retorna_none(self):
        token, start, end = _last_numericish_token("ARMÁRIO")
        self.assertIsNone(token)

    def test_token_deve_terminar_em_digito(self):
        token, start, end = _last_numericish_token("001050761830-")
        self.assertIsNone(token)


class TestClassifyToken(TestCase):
    """Testes para _classify_token()."""

    def test_padrao_atual_bate_regex_strict(self):
        cls, valor = _classify_token("001.050761830-0")
        self.assertEqual(cls, "PADRAO_ATUAL")
        self.assertEqual(valor, "001.050761830-0")

    def test_padrao_atual_por_coercao_13_digitos(self):
        cls, valor = _classify_token("0010507618300")
        self.assertEqual(cls, "PADRAO_ATUAL")
        self.assertEqual(valor, "001.050761830-0")

    def test_padrao_anterior_14_digitos(self):
        cls, valor = _classify_token("00105076183000")
        self.assertEqual(cls, "PADRAO_ANTERIOR")
        self.assertEqual(valor, "00105076183000")

    def test_padrao_anterior_formato_antigo(self):
        cls, valor = _classify_token("001-050-761")
        self.assertEqual(cls, "PADRAO_ANTERIOR")
        self.assertEqual(valor, "001-050-761")

    def test_sem_numero_token_vazio(self):
        cls, valor = _classify_token("")
        self.assertEqual(cls, "SEM_NUMERO")
        self.assertIsNone(valor)

    def test_sem_numero_contem_letras(self):
        cls, valor = _classify_token("001050761830-0ABC")
        self.assertEqual(cls, "SEM_NUMERO")
        self.assertIsNone(valor)


class TestExtract(TestCase):
    """Testes para _extract()."""

    def test_nome_comeca_com_letras_procura_no_fim(self):
        numero, cls, nome_sug, fonte, pos, raw, aplicar = _extract(
            "ARMÁRIO METÁLICO", "001050761830-0"
        )
        # sempre normaliza quando possível (13 dígitos -> PADRAO_ATUAL)
        self.assertEqual(numero, "001.050761830-0")
        self.assertEqual(fonte, "descricao_fim")

    def test_nome_comeca_com_numero_extrai_do_inicio_nome(self):
        numero, cls, nome_sug, fonte, pos, raw, aplicar = _extract(
            "001050761830-0 ARMÁRIO", ""
        )
        self.assertEqual(numero, "001.050761830-0")
        self.assertEqual(fonte, "nome")
        self.assertEqual(nome_sug, "ARMÁRIO")

    def test_nome_sem_numero_descricao_com_numero_no_inicio(self):
        numero, cls, nome_sug, fonte, pos, raw, aplicar = _extract(
            # quando nome começa com letras, a estratégia procura no FINAL
            "ARMÁRIO", "Descrição 001050761830-0"
        )
        self.assertEqual(numero, "001.050761830-0")
        self.assertEqual(fonte, "descricao_fim")

    def test_sem_numero_em_nenhum_lugar(self):
        numero, cls, nome_sug, fonte, pos, raw, aplicar = _extract(
            "ARMÁRIO METÁLICO", "Descrição do bem"
        )
        self.assertEqual(cls, "SEM_NUMERO")
        self.assertIsNone(numero)
        self.assertFalse(aplicar)

    def test_nome_comeca_com_letras_numero_no_fim_nome(self):
        numero, cls, nome_sug, fonte, pos, raw, aplicar = _extract(
            "ARMÁRIO 001050761830-0", ""
        )
        self.assertEqual(numero, "001.050761830-0")
        self.assertEqual(fonte, "nome_fim")

    def test_remove_espacos_duplicados_no_nome_sugerido(self):
        numero, cls, nome_sug, fonte, pos, raw, aplicar = _extract(
            "001050761830-0  ARMÁRIO   METÁLICO", ""
        )
        self.assertEqual(nome_sug, "ARMÁRIO METÁLICO")


class TestSimularExtracaoNumero(TestCase):
    """Testes para simular_extracao_numero()."""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.uo = criar_uo()
        self.ua = criar_ua(uo=self.uo)
        self.gestor = User.objects.create_user(
            username="gestor",
            password="x",
            email="gestor@test.com",
            is_staff=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.admin = type("MockAdmin", (), {"model": BemPatrimonial})()

    def _mk_bem(self, **kwargs):
        defaults = {
            "nome": "Bem Teste",
            "descricao": "Descrição",
            "valor_unitario": 100,
            "marca": "Marca",
            "modelo": "Modelo",
            "numero_processo": "PROC-1",
            "unidade_administrativa": self.ua,
            "criado_por": self.gestor,
            "status": constants.APROVADO,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def test_gera_csv_com_bens_com_numero_patrimonial(self):
        self._mk_bem(
            nome="001050761830-0 ARMÁRIO",
            descricao="",
            numero_patrimonial="001.050761830-0",
        )
        self._mk_bem(
            nome="ARMÁRIO",
            descricao="002050761830-1",
            numero_patrimonial="002.050761830-1",
        )
        request = self.factory.get("/")
        request.user = self.gestor
        response = simular_extracao_numero(self.admin, request, BemPatrimonial.objects.all())
        self.assertIsInstance(response, HttpResponse)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("simulacao_135782_all.csv", response["Content-Disposition"])
        content = response.content.decode("utf-8")
        reader = csv.reader(StringIO(content), delimiter=";")
        rows = list(reader)
        self.assertEqual(len(rows), 3)  # header + 2 bens
        self.assertIn("id", rows[0])
        self.assertIn("numero_extraido", rows[0])

    def test_csv_inclui_todas_colunas_esperadas(self):
        self._mk_bem(
            nome="001050761830-0 ARMÁRIO",
            descricao="",
            numero_patrimonial="001.050761830-0",
        )
        request = self.factory.get("/")
        request.user = self.gestor
        response = simular_extracao_numero(self.admin, request, BemPatrimonial.objects.all())
        content = response.content.decode("utf-8")
        reader = csv.reader(StringIO(content), delimiter=";")
        header = next(reader)
        expected_cols = [
            "id",
            "nome_atual",
            "descricao_atual",
            "numero_patrimonial_atual",
            "numero_extraido",
            "classificacao",
            "fonte",
            "posicao",
            "match_bruto",
            "nome_sugerido",
            "aplicar_auto",
            "elegivel_aplicacao",
        ]
        self.assertEqual(header, expected_cols)

    def test_so_processa_bens_com_numero_patrimonial(self):
        self._mk_bem(
            nome="001050761830-0 ARMÁRIO",
            descricao="",
            numero_patrimonial=None,
        )
        request = self.factory.get("/")
        request.user = self.gestor
        response = simular_extracao_numero(self.admin, request, BemPatrimonial.objects.all())
        content = response.content.decode("utf-8")
        reader = csv.reader(StringIO(content), delimiter=";")
        rows = list(reader)
        self.assertEqual(len(rows), 1)  # apenas header


class TestAplicarExtracaoNumero(TestCase):
    """Testes para aplicar_extracao_numero()."""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.uo = criar_uo()
        self.ua = criar_ua(uo=self.uo)
        self.grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.gestor = User.objects.create_user(
            username="gestor",
            password="x",
            email="gestor@test.com",
            is_staff=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.gestor.groups.add(self.grupo_gestor)
        self.usuario_comum = User.objects.create_user(
            username="comum",
            password="x",
            email="comum@test.com",
            is_staff=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.admin = type("MockAdmin", (), {"model": BemPatrimonial, "admin_site": self.site})()

    def _mk_bem(self, **kwargs):
        defaults = {
            "nome": "Bem Teste",
            "descricao": "Descrição",
            "valor_unitario": 100,
            "marca": "Marca",
            "modelo": "Modelo",
            "numero_processo": "PROC-1",
            "unidade_administrativa": self.ua,
            "criado_por": self.gestor,
            "status": constants.APROVADO,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def _request_com_mensagens(self, method="post", user=None, data=None):
        request = getattr(self.factory, method)("/", data or {})
        request.user = user or self.gestor
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_requer_permissao_gestor_patrimonio(self):
        bem = self._mk_bem(
            nome="ARMÁRIO",
            descricao="Descrição",
            numero_patrimonial=None,
        )
        request = self._request_com_mensagens(user=self.usuario_comum)
        response = aplicar_extracao_numero(
            self.admin, request, BemPatrimonial.objects.filter(pk=bem.pk)
        )
        self.assertIsNone(response)
        messages = list(request._messages)
        self.assertTrue(any("permissão" in str(m).lower() for m in messages))

    def test_mostra_preview_quando_nao_confirma(self):
        bem = self._mk_bem(
            nome="001050761830-0 ARMÁRIO",
            descricao="Descrição",
            numero_patrimonial=None,
        )
        request = self._request_com_mensagens()
        response = aplicar_extracao_numero(
            self.admin, request, BemPatrimonial.objects.filter(pk=bem.pk)
        )
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 200)

    def test_aplica_extracao_quando_confirma(self):
        bem = self._mk_bem(
            nome="001050761830-0 ARMÁRIO",
            descricao="Descrição",
            numero_patrimonial=None,
        )
        request = self._request_com_mensagens(
            data={"confirm": "yes", helpers.ACTION_CHECKBOX_NAME: [str(bem.pk)]}
        )
        response = aplicar_extracao_numero(
            self.admin, request, BemPatrimonial.objects.filter(pk=bem.pk)
        )
        bem.refresh_from_db()
        self.assertEqual(bem.numero_patrimonial, "001.050761830-0")
        self.assertFalse(bem.numero_formato_antigo)
        self.assertFalse(bem.sem_numeracao)

    def test_ignora_bens_que_ja_tem_numero(self):
        bem_com_numero = self._mk_bem(
            nome="001050761830-0 ARMÁRIO",
            descricao="Descrição",
            numero_patrimonial="001.050761830-0",
        )
        bem_sem_numero = self._mk_bem(
            nome="002050761830-1 MESA",
            descricao="Descrição",
            numero_patrimonial=None,
        )
        request = self._request_com_mensagens(
            data={
                "confirm": "yes",
                helpers.ACTION_CHECKBOX_NAME: [str(bem_com_numero.pk), str(bem_sem_numero.pk)],
            }
        )
        aplicar_extracao_numero(
            self.admin,
            request,
            BemPatrimonial.objects.filter(pk__in=[bem_com_numero.pk, bem_sem_numero.pk]),
        )
        bem_com_numero.refresh_from_db()
        bem_sem_numero.refresh_from_db()
        self.assertEqual(bem_com_numero.numero_patrimonial, "001.050761830-0")
        self.assertEqual(bem_sem_numero.numero_patrimonial, "002.050761830-1")

    def test_marca_sem_numeracao_quando_nao_extrai_numero(self):
        bem = self._mk_bem(
            nome="ARMÁRIO METÁLICO",
            descricao="Sem número",
            numero_patrimonial=None,
        )
        request = self._request_com_mensagens(
            data={"confirm": "yes", helpers.ACTION_CHECKBOX_NAME: [str(bem.pk)]}
        )
        aplicar_extracao_numero(
            self.admin, request, BemPatrimonial.objects.filter(pk=bem.pk)
        )
        bem.refresh_from_db()
        self.assertTrue(bem.sem_numeracao)
        self.assertTrue((bem.numero_patrimonial or "").startswith("SEM-NUMERO-"))

    def test_atualiza_nome_quando_sugerido(self):
        bem = self._mk_bem(
            nome="001050761830-0  ARMÁRIO   METÁLICO",
            descricao="Descrição",
            numero_patrimonial=None,
        )
        request = self._request_com_mensagens(
            data={"confirm": "yes", helpers.ACTION_CHECKBOX_NAME: [str(bem.pk)]}
        )
        aplicar_extracao_numero(
            self.admin, request, BemPatrimonial.objects.filter(pk=bem.pk)
        )
        bem.refresh_from_db()
        self.assertEqual(bem.nome, "ARMÁRIO METÁLICO")

    def test_detecta_duplicados_e_nao_aplica(self):
        self._mk_bem(
            nome="001050761830-0 EXISTENTE",
            descricao="Descrição",
            numero_patrimonial="001.050761830-0",
        )
        bem_novo = self._mk_bem(
            nome="001050761830-0 NOVO",
            descricao="Descrição",
            numero_patrimonial=None,
        )
        request = self._request_com_mensagens(
            data={"confirm": "yes", helpers.ACTION_CHECKBOX_NAME: [str(bem_novo.pk)]}
        )
        aplicar_extracao_numero(
            self.admin, request, BemPatrimonial.objects.filter(pk=bem_novo.pk)
        )
        bem_novo.refresh_from_db()
        self.assertIsNone(bem_novo.numero_patrimonial)

    def test_marca_formato_antigo_quando_padrao_anterior(self):
        bem = self._mk_bem(
            nome="00105076183000 MESA",
            descricao="Descrição",
            numero_patrimonial=None,
        )
        request = self._request_com_mensagens(
            data={"confirm": "yes", helpers.ACTION_CHECKBOX_NAME: [str(bem.pk)]}
        )
        aplicar_extracao_numero(
            self.admin, request, BemPatrimonial.objects.filter(pk=bem.pk)
        )
        bem.refresh_from_db()
        self.assertTrue(bem.numero_formato_antigo)
        self.assertEqual(bem.numero_patrimonial, "00105076183000")
