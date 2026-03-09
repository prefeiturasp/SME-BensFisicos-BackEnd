from dados_comuns.tests.auth_test_utils import auth_kwargs
# Cobertura total de bem_patrimonial/admins/actions/extracao_numeros.py

import csv
from io import StringIO
from urllib.parse import urlencode
from unittest.mock import patch

from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.admin import helpers
from django.core.exceptions import ValidationError

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial.admins.bem_patrimonial import BemPatrimonialAdmin
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
from bem_patrimonial.constants import APROVADO
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO
from django.contrib.auth.models import Group


def _request_with_messages(factory, user, method="POST", post_data=None):
    post_data = post_data or {}
    # Corpo urlencoded para getlist(ACTION_CHECKBOX_NAME) funcionar (RequestFactory + multipart não aceita listas)
    if helpers.ACTION_CHECKBOX_NAME in post_data:
        data_tuples = [("confirm", post_data.get("confirm", "yes"))]
        for pk in post_data[helpers.ACTION_CHECKBOX_NAME]:
            data_tuples.append((helpers.ACTION_CHECKBOX_NAME, str(pk)))
        body = urlencode(data_tuples)
        request = factory.post(
            "/admin/",
            body,
            content_type="application/x-www-form-urlencoded",
        )
    else:
        request = factory.post("/admin/", post_data)
    request.user = user
    setattr(request, "session", "session")
    setattr(request, "_messages", FallbackStorage(request))
    return request


class ExtracaoNumerosTest(TestCase):
    """Cobertura de extracao_numeros.py."""

    @classmethod
    def setUpTestData(cls):
        cls.uo = criar_uo(codigo="100", nome="UO 100")
        cls.ua = criar_ua(uo=cls.uo, codigo="001", sigla="UA", nome="UA Teste")
        cls.grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        cls.gestor = Usuario.objects.create_user(
            username="gestor_ext",
            **auth_kwargs("x"),
            unidade_administrativa=cls.ua,
            unidade_orcamentaria=cls.uo,
            is_staff=True,
        )
        cls.gestor.groups.add(cls.grupo_gestor)
        cls.operador = Usuario.objects.create_user(
            username="operador_ext",
            **auth_kwargs("x"),
            unidade_administrativa=cls.ua,
            unidade_orcamentaria=cls.uo,
            is_staff=True,
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.model_admin = BemPatrimonialAdmin(BemPatrimonial, self.site)

    def _criar_bem(self, **kwargs):
        defaults = {
            "nome": "Bem",
            "descricao": "D",
            "valor_unitario": 1,
            "marca": "M",
            "modelo": "X",
            "numero_processo": "P",
            "unidade_administrativa": self.ua,
            "criado_por": self.gestor,
            "status": APROVADO,
            "sem_numeracao": True,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    # --- _digits_only ---
    def test_digits_only_vazio(self):
        self.assertEqual(_digits_only(""), "")
        self.assertEqual(_digits_only(None), "")

    def test_digits_only_remove_nao_digitos(self):
        self.assertEqual(_digits_only("001.050.761.830-0"), "0010507618300")

    # --- _coerce_to_new ---
    def test_coerce_to_new_13_digitos(self):
        self.assertEqual(_coerce_to_new("0010507618300"), "001.050761830-0")
        self.assertEqual(_coerce_to_new("001.050761830-0"), "001.050761830-0")

    def test_coerce_to_new_outros_retorna_none(self):
        self.assertIsNone(_coerce_to_new("123"))
        self.assertIsNone(_coerce_to_new("12345678901234"))

    # --- _first_token ---
    def test_first_token_vazio(self):
        self.assertEqual(_first_token(""), (None, None, None))
        self.assertEqual(_first_token("   "), (None, None, None))

    def test_first_token_ate_espaco(self):
        tok, a, end = _first_token("001050761830-0 ARMÁRIO")
        self.assertEqual(tok, "001050761830-0")
        self.assertEqual(a, 0)
        self.assertIsNotNone(end)

    def test_first_token_ate_barra(self):
        tok, _, _ = _first_token("001.050...-3/ mesa")
        self.assertEqual(tok, "001.050...-3")

    # --- _last_numericish_token ---
    def test_last_numericish_token_vazio(self):
        self.assertEqual(_last_numericish_token(""), (None, None, None))
        self.assertEqual(_last_numericish_token("  "), (None, None, None))

    def test_last_numericish_token_sem_match(self):
        self.assertEqual(_last_numericish_token("abc"), (None, None, None))

    def test_last_numericish_token_token_com_letra_rejeita(self):
        # Token no fim que contém letra é rejeitado (regex não forma token válido)
        self.assertEqual(_last_numericish_token("001.050761830a"), (None, None, None))

    def test_last_numericish_token_valido(self):
        tok, start, end = _last_numericish_token("ARMÁRIO 001.050761830-0")
        self.assertEqual(tok, "001.050761830-0")
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)

    # --- _classify_token ---
    def test_classify_token_vazio(self):
        self.assertEqual(_classify_token(""), ("SEM_NUMERO", None))
        self.assertEqual(_classify_token(None), ("SEM_NUMERO", None))

    def test_classify_token_com_letra(self):
        self.assertEqual(_classify_token("001a050"), ("SEM_NUMERO", None))

    def test_classify_token_padrao_atual(self):
        self.assertEqual(
            _classify_token("001.050761830-0"),
            ("PADRAO_ATUAL", "001.050761830-0"),
        )
        self.assertEqual(
            _classify_token("0010507618300"),
            ("PADRAO_ATUAL", "001.050761830-0"),
        )

    def test_classify_token_padrao_anterior(self):
        cls, val = _classify_token("12345678901234")
        self.assertEqual(cls, "PADRAO_ANTERIOR")
        self.assertEqual(val, "12345678901234")

    # --- _extract ---
    def test_extract_nome_comeca_com_letra_acha_no_fim_nome(self):
        _, cls, _, fonte, _, _, aplicar = _extract(
            "ARMÁRIO METÁLICO 001.050761830-0", ""
        )
        self.assertEqual(cls, "PADRAO_ATUAL")
        self.assertEqual(fonte, "nome_fim")
        self.assertTrue(aplicar)

    def test_extract_nome_comeca_com_letra_acha_na_descricao(self):
        _, _, nome_sug, fonte, _, _, aplicar = _extract(
            "Só letras", "Texto 002.111222333-4"
        )
        self.assertEqual(fonte, "descricao_fim")
        self.assertEqual(nome_sug, "Só letras")
        self.assertTrue(aplicar)

    def test_extract_nome_comeca_com_letra_nao_acha_sem_numero(self):
        numero, cls, _, _, _, _, aplicar = _extract("Só letras aqui", "")
        self.assertIsNone(numero)
        self.assertEqual(cls, "SEM_NUMERO")
        self.assertFalse(aplicar)

    def test_extract_primeiro_token_no_nome(self):
        _, cls, _, fonte, _, _, aplicar = _extract("001.050761830-0 resto do nome", "")
        self.assertEqual(fonte, "nome")
        self.assertEqual(cls, "PADRAO_ATUAL")
        self.assertTrue(aplicar)

    def test_extract_primeiro_token_na_descricao(self):
        # Nome começa com dígito mas primeiro token tem letra (0x); número vem da descrição
        _, _, _, fonte, _, _, aplicar = _extract("0x z", "001.111222333-4 desc")
        self.assertEqual(fonte, "descricao")
        self.assertTrue(aplicar)

    def test_extract_nenhum_token_sem_numero(self):
        numero, cls, _, _, _, _, aplicar = _extract("", "")
        self.assertIsNone(numero)
        self.assertEqual(cls, "SEM_NUMERO")
        self.assertFalse(aplicar)

    # --- simular_extracao_numero ---
    def test_simular_extracao_numero_retorna_csv(self):
        self._criar_bem(
            nome="001.000000001-0 Mesa",
            descricao="",
            numero_patrimonial="001.000000001-0",
            sem_numeracao=False,
        )
        request = self.factory.get("/admin/")
        request.user = self.gestor
        resp = simular_extracao_numero(
            self.model_admin, request, BemPatrimonial.objects.none()
        )
        self.assertEqual(resp["Content-Type"], "text/csv; charset=utf-8")
        content = resp.content.decode("utf-8")
        reader = csv.reader(StringIO(content), delimiter=";")
        rows = list(reader)
        self.assertGreaterEqual(len(rows), 2)  # header + pelo menos 1 bem
        self.assertIn("id", rows[0])
        self.assertIn("numero_extraido", rows[0])

    # --- aplicar_extracao_numero ---
    def test_aplicar_extracao_sem_permissao_retorna_none(self):
        request = _request_with_messages(self.factory, self.operador)
        resp = aplicar_extracao_numero(
            self.model_admin, request, BemPatrimonial.objects.all()
        )
        self.assertIsNone(resp)

    def test_aplicar_extracao_sem_confirm_mostra_preview(self):
        self._criar_bem(nome="001.000000002-0 Cadeira", numero_patrimonial=None)
        request = _request_with_messages(self.factory, self.gestor)
        request.POST = request.POST.copy()
        resp = aplicar_extracao_numero(
            self.model_admin,
            request,
            BemPatrimonial.objects.filter(numero_patrimonial__isnull=True),
        )
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("preview", resp.context_data)
        resp.render()
        self.assertIn("Confirmar aplicação", resp.content.decode())

    def test_aplicar_extracao_preview_com_duplicado(self):
        num_dup = "001.888888888-8"
        self._criar_bem(
            numero_patrimonial=num_dup,
            nome="Já existe",
            sem_numeracao=False,
        )
        bem_dup = self._criar_bem(
            nome=f"Móvel {num_dup}",
            numero_patrimonial="001.000000000-0",
            sem_numeracao=False,
        )
        BemPatrimonial.objects.filter(pk=bem_dup.pk).update(
            numero_patrimonial=None, sem_numeracao=True
        )
        bem_dup.refresh_from_db()
        request = _request_with_messages(self.factory, self.gestor)
        # Mock _extract: retorna num_dup para que existentes já contenha e item fique duplicado
        retorno_extract = (
            num_dup,
            "PADRAO_ATUAL",
            f"Móvel {num_dup}",
            "nome_fim",
            0,
            num_dup,
            True,
        )
        with patch(
            "bem_patrimonial.admins.actions.extracao_numeros._extract",
            return_value=retorno_extract,
        ):
            resp = aplicar_extracao_numero(
                self.model_admin, request, BemPatrimonial.objects.filter(pk=bem_dup.pk)
            )
        self.assertEqual(resp.status_code, 200)
        preview = resp.context_data["preview"]
        self.assertGreater(len(preview), 0)
        self.assertTrue(
            any(p.get("duplicado") for p in preview),
            msg=f"preview={preview}",
        )

    def test_aplicar_extracao_confirm_sem_checkboxes_aviso(self):
        request = _request_with_messages(
            self.factory, self.gestor, post_data={"confirm": "yes"}
        )
        resp = aplicar_extracao_numero(
            self.model_admin, request, BemPatrimonial.objects.none()
        )
        self.assertIsNone(resp)

    def test_aplicar_extracao_sem_numero_marca_sem_numeracao(self):
        bem = self._criar_bem(
            nome="Sem número no texto",
            descricao="Nada",
            numero_patrimonial=None,
            sem_numeracao=False,
        )
        request = _request_with_messages(
            self.factory,
            self.gestor,
            post_data={
                "confirm": "yes",
                helpers.ACTION_CHECKBOX_NAME: [str(bem.pk)],
            },
        )
        aplicar_extracao_numero(
            self.model_admin, request, BemPatrimonial.objects.filter(pk=bem.pk)
        )
        bem.refresh_from_db()
        self.assertTrue(bem.sem_numeracao)

    def test_aplicar_extracao_erro_validation_incrementa_erros(self):
        bem = self._criar_bem(
            nome="001.000000004-0 Erro",
            numero_patrimonial=None,
            sem_numeracao=True,
        )
        request = _request_with_messages(
            self.factory,
            self.gestor,
            post_data={
                "confirm": "yes",
                helpers.ACTION_CHECKBOX_NAME: [str(bem.pk)],
            },
        )
        with patch.object(
            BemPatrimonial, "full_clean", side_effect=ValidationError("erro")
        ):
            aplicar_extracao_numero(
                self.model_admin, request, BemPatrimonial.objects.filter(pk=bem.pk)
            )
        msgs = [str(m) for m in request._messages]
        self.assertTrue(any("Erros:" in m for m in msgs))

    def test_aplicar_extracao_erro_generico_incrementa_erros(self):
        bem = self._criar_bem(
            nome="001.000000005-0 Ex",
            numero_patrimonial=None,
            sem_numeracao=True,
        )
        request = _request_with_messages(
            self.factory,
            self.gestor,
            post_data={
                "confirm": "yes",
                helpers.ACTION_CHECKBOX_NAME: [str(bem.pk)],
            },
        )
        with patch.object(BemPatrimonial, "save", side_effect=RuntimeError("erro")):
            aplicar_extracao_numero(
                self.model_admin, request, BemPatrimonial.objects.filter(pk=bem.pk)
            )
        msgs = [str(m) for m in request._messages]
        self.assertTrue(any("Erros:" in m for m in msgs))
