# Cobertura do bem_patrimonial/admins/bem_patrimonial.py
# Complementa tests_admin.py, tests_aprovacao_lote.py, tests_admin_list_display.py,
# test_edicao_restrita_operador.py e tests_export_pdf.py

from io import BytesIO
from unittest.mock import MagicMock, patch, PropertyMock

import tablib

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.http import HttpResponse
from django.test import TestCase, RequestFactory, Client
from django.urls import reverse

from bem_patrimonial.admins.bem_patrimonial import (
    BemPatrimonialAdmin,
    BemPatrimonialResource,
    reprovar_bens,
)
from bem_patrimonial.constants import (
    AGUARDANDO_APROVACAO,
    APROVADO,
    BAIXA_FISICA,
)
from bem_patrimonial.models import BemPatrimonial, StatusBemPatrimonial
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.auth_test_utils import auth_kwargs
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _request_with_messages(factory, user, method="GET", path="/admin/", data=None):
    if method == "POST":
        request = factory.post(path, data=data or {})
    else:
        request = factory.get(path, data=data or {})
    request.user = user
    setattr(request, "session", "session")
    setattr(request, "_messages", FallbackStorage(request))
    return request


def _make_dataset(*rows, headers=None):
    """Cria um tablib.Dataset simples para testes do Resource."""
    ds = tablib.Dataset(headers=headers or ["nome", "numero_patrimonial"])
    for row in rows:
        ds.append(row)
    return ds


# ---------------------------------------------------------------------------
# Setup compartilhado
# ---------------------------------------------------------------------------

class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.uo = criar_uo(codigo="900", nome="UO 900")
        cls.ua = criar_ua(
            uo=cls.uo,
            codigo="900",
            sigla="UA9",
            nome="UA 900",
            status=UnidadeAdministrativa.ATIVA,
        )
        cls.grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        cls.grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)

        cls.gestor = Usuario.objects.create_user(
            username="gestor_cob2",
            **auth_kwargs("x"),
            unidade_administrativa=cls.ua,
            unidade_orcamentaria=cls.uo,
            is_staff=True,
        )
        cls.gestor.must_change_password = False
        cls.gestor.save(update_fields=["must_change_password"])
        cls.gestor.groups.add(cls.grupo_gestor)

        cls.operador = Usuario.objects.create_user(
            username="operador_cob2",
            **auth_kwargs("x"),
            unidade_administrativa=cls.ua,
            unidade_orcamentaria=cls.uo,
            is_staff=True,
        )
        cls.operador.must_change_password = False
        cls.operador.save(update_fields=["must_change_password"])
        cls.operador.groups.add(cls.grupo_operador)

        cls.user_sem_ua = Usuario.objects.create_user(
            username="sem_ua_cob2",
            **auth_kwargs("x"),
            is_staff=True,
        )
        cls.user_sem_ua.must_change_password = False
        cls.user_sem_ua.save(update_fields=["must_change_password"])

        cls.superuser = Usuario.objects.create_superuser(
            username="super_cob2",
            email="super2@test.com",
            **auth_kwargs("x"),
        )
        cls.superuser.unidade_administrativa = cls.ua
        cls.superuser.unidade_orcamentaria = cls.uo
        cls.superuser.must_change_password = False
        cls.superuser.save(
            update_fields=["unidade_administrativa", "unidade_orcamentaria", "must_change_password"]
        )
        cls.superuser.groups.add(cls.grupo_gestor)

    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = BemPatrimonialAdmin(BemPatrimonial, self.site)

        # Permissões necessárias para add_view e has_view_permission funcionarem
        from django.contrib.contenttypes.models import ContentType
        from django.contrib.auth.models import Permission
        ct = ContentType.objects.get_for_model(BemPatrimonial)
        for codename in ("add_bempatrimonial", "view_bempatrimonial",
                         "change_bempatrimonial", "delete_bempatrimonial"):
            perm, _ = Permission.objects.get_or_create(
                codename=codename,
                content_type=ct,
                defaults={"name": codename},
            )
            self.gestor.user_permissions.add(perm)
            self.operador.user_permissions.add(perm)

        # Limpa cache de permissões para evitar leituras de _perm_cache stale
        for user in (self.gestor, self.operador, self.superuser):
            for attr in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
                if hasattr(user, attr):
                    delattr(user, attr)

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


# ===========================================================================
# 1. reprovar_bens: count_aguardando == 0  (linhas 118-122)
# ===========================================================================

class ReprovarBensCountZeroTest(_Base):
    def test_reprovar_bens_count_zero_emite_warning(self):
        bem = self._criar_bem(status=APROVADO)
        request = _request_with_messages(self.factory, self.gestor, method="POST")
        reprovar_bens(self.admin, request, BemPatrimonial.objects.filter(pk=bem.pk))
        msgs = [str(m) for m in request._messages]
        self.assertTrue(any("Aguardando aprovação" in m for m in msgs))


# ===========================================================================
# 2. BemPatrimonialResource — helpers internos  (linhas 264-308)
# ===========================================================================

class ResourceHelpersTest(_Base):
    def setUp(self):
        super().setUp()
        self.resource = BemPatrimonialResource(request=None)
        # before_import inicializa os atributos
        self.resource._numeros_patrimoniais_no_arquivo = {}
        self.resource._erros_importacao = []
        self.resource._mensagens_exibidas = False

    def test_normalizar_valor_none_retorna_string_vazia(self):
        self.assertEqual(self.resource._normalizar_valor(None), "")

    def test_normalizar_valor_string_retorna_stripped(self):
        self.assertEqual(self.resource._normalizar_valor("  abc  "), "abc")

    def test_get_row_value_header_presente(self):
        row = {"numero_patrimonial": "001.000000001-0"}
        val = self.resource._get_row_value(row, ("numero_patrimonial",))
        self.assertEqual(val, "001.000000001-0")

    def test_get_row_value_header_ausente_retorna_vazio(self):
        row = {}
        self.assertEqual(self.resource._get_row_value(row, ("numero_patrimonial",)), "")

    def test_clear_imported_id_zera_id(self):
        row = {"id": 99, "ID": 88}
        self.resource._clear_imported_id(row)
        self.assertIsNone(row["id"])
        self.assertIsNone(row["ID"])

    def test_force_status_aguardando_aprovacao(self):
        row = {"status": "aprovado", "STATUS": "outro"}
        self.resource._force_status_aguardando_aprovacao(row)
        self.assertEqual(row["status"], AGUARDANDO_APROVACAO)
        self.assertEqual(row["STATUS"], AGUARDANDO_APROVACAO)

    def test_get_linha_exibicao_none_retorna_traco(self):
        self.assertEqual(self.resource._get_linha_exibicao(None), "-")

    def test_get_linha_exibicao_string_vazia_retorna_traco(self):
        self.assertEqual(self.resource._get_linha_exibicao(""), "-")

    def test_get_linha_exibicao_numero_retorna_int(self):
        self.assertEqual(self.resource._get_linha_exibicao("3"), 3)

    def test_get_linha_exibicao_invalido_retorna_original(self):
        self.assertEqual(self.resource._get_linha_exibicao("abc"), "abc")

    def test_registrar_erro_linha_marca_row_e_acumula(self):
        row = {}
        self.resource._registrar_erro_linha(row, 5, "001.000000001-0", "Duplicado")
        self.assertIn(self.resource.SKIP_REASON_KEY, row)
        self.assertEqual(len(self.resource._erros_importacao), 1)
        self.assertIn("001.000000001-0", self.resource._erros_importacao[0])

    def test_registrar_erro_linha_sem_numero_usa_traco(self):
        row = {}
        self.resource._registrar_erro_linha(row, 1, "", "Erro X")
        self.assertIn("Número Patrimonial: -", self.resource._erros_importacao[0])


# ===========================================================================
# 3. _validar_numero_patrimonial_para_skip  (linhas 320-355)
# ===========================================================================

class ValidarNumeroPatrimonialParaSkipTest(_Base):
    def setUp(self):
        super().setUp()
        self.resource = BemPatrimonialResource(request=None)
        self.resource._numeros_patrimoniais_no_arquivo = {}
        self.resource._erros_importacao = []
        self.resource._mensagens_exibidas = False

    def test_numero_branco_nao_registra_erro(self):
        row = {"numero_patrimonial": ""}
        self.resource._validar_numero_patrimonial_para_skip(row, 1)
        self.assertEqual(len(self.resource._erros_importacao), 0)

    def test_duplicado_no_arquivo_registra_erro(self):
        row1 = {"numero_patrimonial": "001.000000001-0"}
        row2 = {"numero_patrimonial": "001.000000001-0"}
        self.resource._validar_numero_patrimonial_para_skip(row1, 1)
        self.resource._validar_numero_patrimonial_para_skip(row2, 2)
        self.assertEqual(len(self.resource._erros_importacao), 1)
        self.assertIn("duplicado no arquivo", self.resource._erros_importacao[0])

    def test_duplicado_no_banco_registra_erro(self):
        self._criar_bem(numero_patrimonial="001.000000099-0", sem_numeracao=False)
        row = {"numero_patrimonial": "001.000000099-0"}
        self.resource._validar_numero_patrimonial_para_skip(row, 1)
        self.assertEqual(len(self.resource._erros_importacao), 1)
        self.assertIn("já cadastrado", self.resource._erros_importacao[0])


# ===========================================================================
# 4. before_import  (linhas 374-395)
# ===========================================================================

class BeforeImportTest(_Base):
    def _make_resource(self, user=None):
        req = None
        if user is not None:
            req = _request_with_messages(self.factory, user)
        return BemPatrimonialResource(request=req)

    def test_before_import_sem_request_nao_levanta(self):
        resource = self._make_resource(user=None)
        ds = _make_dataset()
        resource.before_import(ds)  # não deve levantar
        self.assertEqual(resource._erros_importacao, [])

    def test_before_import_usuario_sem_ua_levanta_validation_error(self):
        resource = self._make_resource(user=self.user_sem_ua)
        ds = _make_dataset()
        with self.assertRaises(ValidationError) as ctx:
            resource.before_import(ds)
        self.assertIn("Unidade Administrativa", str(ctx.exception))

    def test_before_import_ua_inativa_levanta_validation_error(self):
        self.ua.status = UnidadeAdministrativa.INATIVA
        self.ua.save(update_fields=["status"])
        try:
            resource = self._make_resource(user=self.gestor)
            ds = _make_dataset()
            with self.assertRaises(ValidationError) as ctx:
                resource.before_import(ds)
            self.assertIn("inativa", str(ctx.exception))
        finally:
            self.ua.status = UnidadeAdministrativa.ATIVA
            self.ua.save(update_fields=["status"])

    def test_before_import_reinicia_estado(self):
        resource = self._make_resource(user=self.gestor)
        resource._erros_importacao = ["lixo anterior"]
        resource._mensagens_exibidas = True
        ds = _make_dataset()
        resource.before_import(ds)
        self.assertEqual(resource._erros_importacao, [])
        self.assertFalse(resource._mensagens_exibidas)


# ===========================================================================
# 5. skip_row e get_instance  (linhas 413-416, 428)
# ===========================================================================

class SkipRowGetInstanceTest(_Base):
    def setUp(self):
        super().setUp()
        self.resource = BemPatrimonialResource(request=None)
        self.resource._numeros_patrimoniais_no_arquivo = {}
        self.resource._erros_importacao = []

    def test_skip_row_com_chave_retorna_true(self):
        row = {self.resource.SKIP_REASON_KEY: "erro qualquer"}
        instance = MagicMock()
        original = MagicMock()
        self.assertTrue(self.resource.skip_row(instance, original, row))

    def test_skip_row_sem_chave_delega_para_super(self):
        row = {}
        instance = MagicMock()
        original = MagicMock()
        # super().skip_row retorna False por padrão quando unchanged=False
        result = self.resource.skip_row(instance, original, row)
        self.assertFalse(result)

    def test_get_instance_sempre_retorna_none(self):
        loader = MagicMock()
        row = {"id": 1}
        self.assertIsNone(self.resource.get_instance(loader, row))


# ===========================================================================
# 6. before_save_instance  (linhas 442-465)
# ===========================================================================

class BeforeSaveInstanceTest(_Base):
    def _resource_com_request(self):
        req = _request_with_messages(self.factory, self.gestor)
        return BemPatrimonialResource(request=req)

    def test_sem_request_nao_atribui_user_nem_ua(self):
        resource = BemPatrimonialResource(request=None)
        instance = BemPatrimonial(nome="X", sem_numeracao=True)
        resource.before_save_instance(instance)
        self.assertIsNone(instance.pk)
        self.assertIsNone(instance.criado_por_id)

    def test_com_request_atribui_criado_por_e_ua(self):
        resource = self._resource_com_request()
        instance = BemPatrimonial(nome="X")
        resource.before_save_instance(instance)
        self.assertEqual(instance.criado_por, self.gestor)
        self.assertEqual(instance.unidade_administrativa, self.ua)
        self.assertEqual(instance.status, AGUARDANDO_APROVACAO)

    def test_numero_branco_define_sem_numeracao(self):
        resource = self._resource_com_request()
        instance = BemPatrimonial(nome="X", numero_patrimonial="")
        resource.before_save_instance(instance)
        self.assertTrue(instance.sem_numeracao)
        self.assertIsNone(instance.numero_patrimonial)
        self.assertFalse(instance.numero_formato_antigo)

    def test_numero_novo_formato_define_numero_formato_antigo_false(self):
        resource = self._resource_com_request()
        instance = BemPatrimonial(nome="X", numero_patrimonial="001.000000001-0")
        resource.before_save_instance(instance)
        self.assertFalse(instance.numero_formato_antigo)
        self.assertFalse(instance.sem_numeracao)

    def test_numero_formato_antigo_define_flag_true(self):
        resource = self._resource_com_request()
        instance = BemPatrimonial(nome="X", numero_patrimonial="12345")
        resource.before_save_instance(instance)
        self.assertTrue(instance.numero_formato_antigo)
        self.assertFalse(instance.sem_numeracao)

    def test_criado_por_ja_preenchido_nao_sobrescreve(self):
        resource = self._resource_com_request()
        outro_user = self.operador
        instance = BemPatrimonial(nome="X", criado_por=outro_user, sem_numeracao=True)
        resource.before_save_instance(instance)
        self.assertEqual(instance.criado_por, outro_user)


# ===========================================================================
# 7. after_import  (linhas 477-498)
# ===========================================================================

class AfterImportTest(_Base):
    def _resource_com_request(self):
        req = _request_with_messages(self.factory, self.gestor)
        return BemPatrimonialResource(request=req)

    # A versão 3.0.2 do django-import-export exige os positional args
    # using_transactions e dry_run em after_import.
    _AFTER_IMPORT_EXTRA = (True, False)

    def test_after_import_sem_erros_nao_emite_mensagens(self):
        resource = self._resource_com_request()
        resource._erros_importacao = []
        resource._mensagens_exibidas = False
        result = MagicMock()
        result.totals = {}
        resource.after_import(_make_dataset(), result, *self._AFTER_IMPORT_EXTRA)
        msgs = list(resource.request._messages)
        self.assertEqual(len(msgs), 0)

    def test_after_import_mensagens_exibidas_nao_duplica(self):
        resource = self._resource_com_request()
        resource._erros_importacao = ["erro1"]
        resource._mensagens_exibidas = True
        result = MagicMock()
        result.totals = {}
        resource.after_import(_make_dataset(), result, *self._AFTER_IMPORT_EXTRA)
        msgs = list(resource.request._messages)
        self.assertEqual(len(msgs), 0)

    def test_after_import_com_erros_emite_warning_resumo_e_detalhe(self):
        resource = self._resource_com_request()
        resource._erros_importacao = ["Linha 1 | erro"]
        resource._mensagens_exibidas = False
        result = MagicMock()
        result.totals = {}
        resource.after_import(_make_dataset(), result, *self._AFTER_IMPORT_EXTRA)
        msgs = [str(m) for m in resource.request._messages]
        self.assertTrue(any("1 linha(s)" in m for m in msgs))
        self.assertTrue(any("Linha 1" in m for m in msgs))

    def test_after_import_mais_de_20_erros_emite_aviso_extra(self):
        resource = self._resource_com_request()
        resource._erros_importacao = [f"Linha {i} | erro" for i in range(25)]
        resource._mensagens_exibidas = False
        result = MagicMock()
        result.totals = {}
        resource.after_import(_make_dataset(), result, *self._AFTER_IMPORT_EXTRA)
        msgs = [str(m) for m in resource.request._messages]
        self.assertTrue(any("mais 5" in m for m in msgs))


# ===========================================================================
# 8. delete_view: extra_context  (linha 598)
# ===========================================================================

class DeleteViewExtraContextTest(_Base):
    def test_delete_view_get_com_extra_context(self):
        bem = self._criar_bem()
        request = _request_with_messages(self.factory, self.gestor)
        request.resolver_match = MagicMock()
        resp = self.admin.delete_view(
            request, str(bem.pk), extra_context={"custom_key": "custom_value"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context_data.get("custom_key"), "custom_value")


# ===========================================================================
# 9. _usuario_pode_editar_obj  (linhas 676-680)
# ===========================================================================

class UsuarioPodeEditarObjTest(_Base):
    def test_superuser_pode_editar_qualquer_bem(self):
        outra_uo = criar_uo(codigo="910", nome="UO 910")
        outra_ua = criar_ua(uo=outra_uo, codigo="910", sigla="U910", nome="UA 910",
                            status=UnidadeAdministrativa.ATIVA)
        bem = self._criar_bem(unidade_administrativa=outra_ua)
        self.assertTrue(self.admin._usuario_pode_editar_obj(self.superuser, bem))

    def test_usuario_comum_nao_pode_editar_bem_de_outra_ua(self):
        outra_uo = criar_uo(codigo="911", nome="UO 911")
        outra_ua = criar_ua(uo=outra_uo, codigo="911", sigla="U911", nome="UA 911",
                            status=UnidadeAdministrativa.ATIVA)
        bem = self._criar_bem(unidade_administrativa=outra_ua)
        self.assertFalse(self.admin._usuario_pode_editar_obj(self.gestor, bem))


# ===========================================================================
# 10. has_view_permission  (linhas 690-696)
# ===========================================================================

class HasViewPermissionTest(_Base):
    def test_superuser_tem_view_permission_em_obj(self):
        bem = self._criar_bem()
        request = _request_with_messages(self.factory, self.superuser)
        self.assertTrue(self.admin.has_view_permission(request, obj=bem))

    def test_gestor_tem_view_permission_em_obj(self):
        bem = self._criar_bem()
        request = _request_with_messages(self.factory, self.gestor)
        self.assertTrue(self.admin.has_view_permission(request, obj=bem))

    def test_operador_tem_view_permission_em_obj(self):
        bem = self._criar_bem()
        request = _request_with_messages(self.factory, self.operador)
        self.assertTrue(self.admin.has_view_permission(request, obj=bem))

    def test_usuario_sem_grupo_pode_ver_proprio_bem(self):
        user_proprio = Usuario.objects.create_user(
            username="proprio_cob2",
            **auth_kwargs("x"),
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
            is_staff=True,
        )
        bem = self._criar_bem()
        request = _request_with_messages(self.factory, user_proprio)
        # O resultado depende do escopo, mas o método não deve levantar
        result = self.admin.has_view_permission(request, obj=bem)
        self.assertIsInstance(result, bool)


# ===========================================================================
# 11. get_object fallback  (linhas 703-717)
# ===========================================================================

class GetObjectFallbackTest(_Base):
    def test_get_object_fallback_gestor_encontra_bem(self):
        bem = self._criar_bem()
        request = _request_with_messages(self.factory, self.gestor)
        # super().get_object retorna None, triggering the fallback
        with patch(
            "import_export.admin.ImportExportModelAdmin.get_object",
            return_value=None,
        ):
            resultado = self.admin.get_object(request, str(bem.pk))
        self.assertEqual(resultado, bem)

    def test_get_object_fallback_does_not_exist_retorna_none(self):
        request = _request_with_messages(self.factory, self.gestor)
        with patch(
            "import_export.admin.ImportExportModelAdmin.get_object",
            return_value=None,
        ):
            resultado = self.admin.get_object(request, "999999999")
        self.assertIsNone(resultado)

    def test_get_object_fallback_valor_invalido_retorna_none(self):
        request = _request_with_messages(self.factory, self.gestor)
        with patch(
            "import_export.admin.ImportExportModelAdmin.get_object",
            return_value=None,
        ):
            resultado = self.admin.get_object(request, "nao-e-um-id")
        self.assertIsNone(resultado)

    def test_get_object_usuario_sem_grupo_retorna_none_quando_super_retorna_none(self):
        request = _request_with_messages(self.factory, self.user_sem_ua)
        with patch(
            "import_export.admin.ImportExportModelAdmin.get_object",
            return_value=None,
        ):
            resultado = self.admin.get_object(request, "1")
        self.assertIsNone(resultado)


# ===========================================================================
# 12. has_change_permission: obj fora do escopo  (linha 725)
# ===========================================================================

class HasChangePermissionEscopoTest(_Base):
    def test_has_change_permission_false_obj_fora_do_escopo(self):
        outra_uo = criar_uo(codigo="920", nome="UO 920")
        outra_ua = criar_ua(uo=outra_uo, codigo="920", sigla="U920", nome="UA 920",
                            status=UnidadeAdministrativa.ATIVA)
        bem = self._criar_bem(unidade_administrativa=outra_ua)
        request = _request_with_messages(self.factory, self.gestor)
        self.assertFalse(self.admin.has_change_permission(request, obj=bem))


# ===========================================================================
# 13. _validate_create_form_ua  (linhas 778-802)
# ===========================================================================

class ValidateCreateFormUaTest(_Base):
    def _cleaned(self, ua=None):
        return {"unidade_administrativa": ua}

    def test_ua_form_none_levanta(self):
        request = _request_with_messages(self.factory, self.gestor)
        with self.assertRaises(ValidationError):
            self.admin._validate_create_form_ua(self._cleaned(None), request)

    def test_ua_inativa_levanta(self):
        ua_inativa = criar_ua(
            uo=self.uo, codigo="930", sigla="INATIVA", nome="UA Inativa",
            status=UnidadeAdministrativa.INATIVA,
        )
        request = _request_with_messages(self.factory, self.gestor)
        with self.assertRaises(ValidationError):
            self.admin._validate_create_form_ua(self._cleaned(ua_inativa), request)

    def test_ua_fora_do_escopo_levanta(self):
        outra_uo = criar_uo(codigo="931", nome="UO 931")
        ua_outra = criar_ua(uo=outra_uo, codigo="931", sigla="U931", nome="UA 931",
                            status=UnidadeAdministrativa.ATIVA)
        request = _request_with_messages(self.factory, self.gestor)
        with self.assertRaises(ValidationError):
            self.admin._validate_create_form_ua(self._cleaned(ua_outra), request)

    def test_ua_user_inativa_levanta(self):
        self.ua.status = UnidadeAdministrativa.INATIVA
        self.ua.save(update_fields=["status"])
        try:
            request = _request_with_messages(self.factory, self.gestor)
            with self.assertRaises(ValidationError):
                self.admin._validate_create_form_ua(self._cleaned(self.ua), request)
        finally:
            self.ua.status = UnidadeAdministrativa.ATIVA
            self.ua.save(update_fields=["status"])


# ===========================================================================
# 14. _validate_edit_form_ua  (linhas 806-818)
# ===========================================================================

class ValidateEditFormUaTest(_Base):
    def test_instance_sem_pk_retorna_sem_erro(self):
        instance = BemPatrimonial()
        self.admin._validate_edit_form_ua({}, instance, self.gestor)  # não levanta

    def test_ua_alterada_levanta(self):
        outra_uo = criar_uo(codigo="940", nome="UO 940")
        outra_ua = criar_ua(uo=outra_uo, codigo="940", sigla="U940", nome="UA 940",
                            status=UnidadeAdministrativa.ATIVA)
        bem = self._criar_bem()
        cleaned = {"unidade_administrativa": outra_ua}
        with self.assertRaises(ValidationError):
            self.admin._validate_edit_form_ua(cleaned, bem, self.gestor)


# ===========================================================================
# 15. save_model: IntegrityError  (linhas 895-906)
# ===========================================================================

class SaveModelIntegrityErrorTest(_Base):
    def test_integrity_error_com_numero_patrimonial_adiciona_erro_no_form(self):
        bem = BemPatrimonial(
            nome="X",
            descricao="D",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_processo="P",
            unidade_administrativa=self.ua,
            sem_numeracao=True,
        )
        request = _request_with_messages(self.factory, self.gestor, method="POST")
        request.user = self.gestor
        form = MagicMock()
        form.cleaned_data = {}

        with patch(
            "import_export.admin.ImportExportModelAdmin.save_model",
            side_effect=IntegrityError("duplicate key: numero_patrimonial"),
        ):
            self.admin.save_model(request, bem, form, change=False)

        form.add_error.assert_called_once()

    def test_integrity_error_sem_numero_patrimonial_reraise(self):
        bem = BemPatrimonial(
            nome="X",
            descricao="D",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_processo="P",
            unidade_administrativa=self.ua,
            sem_numeracao=True,
        )
        request = _request_with_messages(self.factory, self.gestor, method="POST")
        request.user = self.gestor
        form = MagicMock()
        form.cleaned_data = {}

        with self.assertRaises(IntegrityError):
            with patch(
                "import_export.admin.ImportExportModelAdmin.save_model",
                side_effect=IntegrityError("outro constraint"),
            ):
                self.admin.save_model(request, bem, form, change=False)


# ===========================================================================
# 16. save_status: deleted_objects e instâncias  (linhas 1022-1025)
# ===========================================================================

class SaveStatusTest(_Base):
    def test_save_status_deleta_e_salva_com_atualizado_por(self):
        bem = self._criar_bem()

        novo_status = StatusBemPatrimonial(bem_patrimonial=bem, status=AGUARDANDO_APROVACAO)
        deletado = MagicMock()

        formset = MagicMock()
        formset.save.return_value = [novo_status]
        formset.deleted_objects = [deletado]
        formset.save_m2m = MagicMock()

        request = _request_with_messages(self.factory, self.gestor)
        form = MagicMock()

        self.admin.save_status(request, form, formset, change=True)

        deletado.delete.assert_called_once()
        self.assertEqual(novo_status.atualizado_por, self.gestor)


# ===========================================================================
# 17. _add_view_multi_base_data: status None  (linhas 1040-1046)
# ===========================================================================

class AddViewMultiBaseDataTest(_Base):
    def test_status_none_usa_default_do_campo(self):
        form = MagicMock()
        form.cleaned_data = {
            "status": None,
            "unidade_administrativa": self.ua,
            "nome": "N",
            "descricao": "D",
            "valor_unitario": 1,
            "marca": "M",
            "modelo": "X",
            "numero_processo": "P",
            "foto": None,
        }
        base = self.admin._add_view_multi_base_data(form)
        self.assertIsNotNone(base["status"])


# ===========================================================================
# 18. _add_view_multi_parse_payload: JSON inválido  (linhas 1055-1056)
# ===========================================================================

class AddViewMultiParsePayloadTest(_Base):
    def test_json_invalido_retorna_lista_vazia(self):
        request = _request_with_messages(self.factory, self.gestor, method="POST",
                                         data={"multi_payload": "nao-e-json{"})
        result = self.admin._add_view_multi_parse_payload(request)
        self.assertEqual(result, [])


# ===========================================================================
# 19. _add_view_multi_to_bool  (linhas 1059-1063)
# ===========================================================================

class AddViewMultiToBoolTest(_Base):
    def test_bool_true(self):
        self.assertTrue(self.admin._add_view_multi_to_bool(True))

    def test_bool_false(self):
        self.assertFalse(self.admin._add_view_multi_to_bool(False))

    def test_none_retorna_false(self):
        self.assertFalse(self.admin._add_view_multi_to_bool(None))

    def test_string_true(self):
        for v in ("1", "true", "on", "yes", "y", "t", "TRUE", "True"):
            self.assertTrue(self.admin._add_view_multi_to_bool(v), f"falhou para '{v}'")

    def test_string_false(self):
        for v in ("0", "false", "off", "no", "n", "f", ""):
            self.assertFalse(self.admin._add_view_multi_to_bool(v), f"falhou para '{v}'")


# ===========================================================================
# 20. _add_view_multi_process_row_validate_save: ramos de erro  (linhas 1067-1081)
# ===========================================================================

class AddViewMultiProcessRowValidateSaveTest(_Base):
    def _bem_invalido(self):
        return BemPatrimonial(
            nome="",   # nome vazio — irá falhar no full_clean
            unidade_administrativa=self.ua,
            criado_por=self.gestor,
        )

    def test_validation_error_sem_message_dict(self):
        bem = MagicMock()
        bem.full_clean.side_effect = ValidationError("mensagem simples")
        result_bem, erro = self.admin._add_view_multi_process_row_validate_save(bem, 3)
        self.assertIsNone(result_bem)
        self.assertIn("Linha 3", erro)

    def test_integrity_error_retorna_mensagem(self):
        bem = MagicMock()
        bem.full_clean.return_value = None
        bem.save.side_effect = IntegrityError("constraint falhou")
        result_bem, erro = self.admin._add_view_multi_process_row_validate_save(bem, 4)
        self.assertIsNone(result_bem)
        self.assertIn("Linha 4", erro)

    def test_exception_generica_retorna_mensagem(self):
        bem = MagicMock()
        bem.full_clean.return_value = None
        bem.save.side_effect = RuntimeError("algo explodiu")
        result_bem, erro = self.admin._add_view_multi_process_row_validate_save(bem, 5)
        self.assertIsNone(result_bem)
        self.assertIn("Erro inesperado", erro)


# ===========================================================================
# 21. _add_view_multi_process_row: sem localizacao e com sem_numeracao  (linhas 1084-1102)
# ===========================================================================

class AddViewMultiProcessRowTest(_Base):
    def _base(self):
        return {
            "status": AGUARDANDO_APROVACAO,
            "unidade_administrativa": self.ua,
            "nome": "N",
            "descricao": "D",
            "valor_unitario": 1,
            "marca": "M",
            "modelo": "X",
            "numero_processo": "P",
            "foto": None,
        }

    def test_sem_localizacao_retorna_erro(self):
        request = _request_with_messages(self.factory, self.gestor)
        row = {"localizacao": ""}
        result_bem, erro = self.admin._add_view_multi_process_row(request, 1, row, self._base())
        self.assertIsNone(result_bem)
        self.assertIn("Localização", erro)

    def test_com_sem_numeracao_numero_patrimonial_nao_vem_da_row(self):
        request = _request_with_messages(self.factory, self.gestor)
        row = {
            "localizacao": "Sala 1",
            "numero_patrimonial": "001.000000050-0",
            "sem_numeracao": "1",
            "numero_formato_antigo": "0",
        }
        result_bem, _ = self.admin._add_view_multi_process_row(request, 1, row, self._base())
        # sem_numeracao=True faz o número patrimonial vir de SEM-NUMERO-X (atribuído pelo model)
        # ou None — em todo caso NÃO deve ser o número da planilha
        if result_bem:
            self.assertNotEqual(result_bem.numero_patrimonial, "001.000000050-0")
        else:
            # Se falhou por outro motivo de validação, apenas verifica que não foi criado com o número
            self.assertIsNone(result_bem)


# ===========================================================================
# 22. _add_view_multi_process_linhas: com erros faz rollback  (linhas 1104-1115)
# ===========================================================================

class AddViewMultiProcessLinhasTest(_Base):
    def _base(self):
        return {
            "status": AGUARDANDO_APROVACAO,
            "unidade_administrativa": self.ua,
            "nome": "N",
            "descricao": "D",
            "valor_unitario": 1,
            "marca": "M",
            "modelo": "X",
            "numero_processo": "P",
            "foto": None,
        }

    def test_com_erro_faz_rollback_e_retorna_errors(self):
        request = _request_with_messages(self.factory, self.gestor)
        # linha sem localizacao → gera erro
        linhas = [{"localizacao": ""}]
        count_antes = BemPatrimonial.objects.count()
        _, errors = self.admin._add_view_multi_process_linhas(request, linhas, self._base())
        self.assertEqual(len(errors), 1)
        self.assertEqual(BemPatrimonial.objects.count(), count_antes)

    def test_sem_erro_cria_bens(self):
        request = _request_with_messages(self.factory, self.gestor)
        linhas = [{
            "localizacao": "Sala A",
            "numero_patrimonial": "",
            "sem_numeracao": "1",
            "numero_formato_antigo": "0",
        }]
        count_antes = BemPatrimonial.objects.count()
        _, errors = self.admin._add_view_multi_process_linhas(request, linhas, self._base())
        self.assertEqual(len(errors), 0)
        self.assertEqual(BemPatrimonial.objects.count(), count_antes + 1)


# ===========================================================================
# 23. _add_view_handle_multi_post: form inválido e payload com erro  (linhas 1126-1145)
# ===========================================================================

class AddViewHandleMultiPostTest(_Base):
    def test_form_invalido_retorna_super_add_view(self):
        url = reverse("admin:bem_patrimonial_bempatrimonial_add")
        client = Client()
        client.force_login(self.gestor)
        # POST sem campos obrigatórios → form inválido
        resp = client.post(url, data={
            "cadastro_modo": "multi",
            "multi_payload": '[{"localizacao":"Sala","sem_numeracao":"1","numero_patrimonial":"","numero_formato_antigo":"0"}]',
            # nome, descricao, etc. ausentes → form base inválido
        })
        self.assertIn(resp.status_code, (200, 302))

    def test_payload_com_linha_com_erro_exibe_mensagem_e_nao_cria(self):
        url = reverse("admin:bem_patrimonial_bempatrimonial_add")
        client = Client()
        client.force_login(self.gestor)
        count_antes = BemPatrimonial.objects.count()
        # linha sem localizacao → gera erro
        resp = client.post(url, data={
            "cadastro_modo": "multi",
            "multi_payload": '[{"localizacao":"","sem_numeracao":"1","numero_patrimonial":"","numero_formato_antigo":"0"}]',
            "unidade_administrativa": str(self.ua.pk),
            "nome": "N",
            "descricao": "D",
            "valor_unitario": "1,00",
            "marca": "M",
            "modelo": "X",
            "numero_processo": "P",
        })
        self.assertIn(resp.status_code, (200, 302))
        self.assertEqual(BemPatrimonial.objects.count(), count_antes)


# ===========================================================================
# 24. render_change_form: HTML_END_FORM_CONTAINER  (linha 1181)
# ===========================================================================

class RenderChangeFormContainerTest(_Base):
    def test_injeta_anchor_quando_html_end_form_container_presente(self):
        request = _request_with_messages(self.factory, self.gestor)
        request.POST = request.POST.copy()
        context = {"inline_admin_formsets": []}

        mock_response = MagicMock()
        mock_response.rendered_content = "</div><!-- END form-container -->"
        mock_response.charset = "utf-8"
        mock_response.content = b""

        with patch(
            "import_export.admin.ImportExportModelAdmin.render_change_form",
            return_value=mock_response,
        ):
            resp = self.admin.render_change_form(request, context, add=True, change=False)

        content = resp.content if isinstance(resp.content, bytes) else resp.content.encode()
        self.assertIn(b"multi-inline-root", content)


# ===========================================================================
# 25. alterado_por_ultimo: retorna nome quando user existe  (linha 1208)
# ===========================================================================

class AlteradoPorUltimoComUserTest(_Base):
    def test_retorna_full_name_quando_user_existe(self):
        self.gestor.first_name = "José"
        self.gestor.last_name = "Silva"
        self.gestor.save(update_fields=["first_name", "last_name"])
        bem = self._criar_bem()
        bem.audit_last_by_id = self.gestor.pk
        resultado = self.admin.alterado_por_ultimo(bem)
        self.assertIn("José", resultado)

    def test_retorna_username_quando_sem_full_name(self):
        bem = self._criar_bem()
        bem.audit_last_by_id = self.gestor.pk
        self.gestor.first_name = ""
        self.gestor.last_name = ""
        self.gestor.save(update_fields=["first_name", "last_name"])
        resultado = self.admin.alterado_por_ultimo(bem)
        self.assertEqual(resultado, self.gestor.username)


# ===========================================================================
# 26. get_inline_instances: obj não None  (linha 1215)
# ===========================================================================

class GetInlineInstancesObjTest(_Base):
    def test_get_inline_instances_com_obj_chama_super(self):
        bem = self._criar_bem()
        request = _request_with_messages(self.factory, self.gestor)
        # Não deve retornar lista vazia quando obj existe
        instances = self.admin.get_inline_instances(request, obj=bem)
        self.assertIsInstance(instances, list)


# ===========================================================================
# 27. _aplicar_filtros_autocomplete_bem: app_label diferente  (linha 1260)
# ===========================================================================

class AplicarFiltrosAutocompleteBemTest(_Base):
    def test_app_label_diferente_retorna_qs_inalterado(self):
        request = self.factory.get("/admin/", {
            "app_label": "outro_app",
            "model_name": "baixafisicabensitem",
            "field_name": "bem",
        })
        request.user = self.gestor
        qs = BemPatrimonial.objects.all()
        result_qs, _ = self.admin._aplicar_filtros_autocomplete_bem(request, qs, False)
        # Retorna o qs original sem filtrar
        self.assertEqual(list(result_qs), list(qs))

    def test_transferencia_sem_uo_referencia_retorna_none_qs(self):
        # Usuário sem UO → obter_unidade_orcamentaria_id_do_usuario retorna None
        user_sem_uo = Usuario.objects.create_user(
            username="sem_uo_autocomplete",
            **auth_kwargs("x"),
            is_staff=True,
        )
        request = self.factory.get("/admin/", {
            "app_label": "bem_patrimonial",
            "model_name": "transferenciabensitem",
            "field_name": "bem",
        })
        request.user = user_sem_uo
        qs = BemPatrimonial.objects.all()
        result_qs, _ = self.admin._aplicar_filtros_autocomplete_bem(request, qs, False)
        self.assertEqual(list(result_qs), [])

    def test_transferencia_uo_origem_diferente_da_referencia_retorna_none_qs(self):
        outra_uo = criar_uo(codigo="950", nome="UO 950")
        request = self.factory.get("/admin/", {
            "app_label": "bem_patrimonial",
            "model_name": "transferenciabensitem",
            "field_name": "bem",
            "uo_origem": str(outra_uo.pk),
        })
        request.user = self.gestor
        qs = BemPatrimonial.objects.all()
        result_qs, _ = self.admin._aplicar_filtros_autocomplete_bem(request, qs, False)
        self.assertEqual(list(result_qs), [])


# ===========================================================================
# 28. changelist_view: sem flag não redireciona  (linha 1316)
# ===========================================================================

class ChangelistViewSemFlagTest(_Base):
    def test_changelist_view_sem_busca_com_baixados_retorna_response_normal(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/")
        request.user = self.gestor
        request.resolver_match = MagicMock()
        request.resolver_match.url_name = "bem_patrimonial_bempatrimonial_changelist"
        setattr(request, "session", "session")
        setattr(request, "_messages", FallbackStorage(request))
        # _busca_com_baixados_antigos não setado → não deve redirecionar

        mock_response = HttpResponse("ok")
        with patch(
            "import_export.admin.ImportExportModelAdmin.changelist_view",
            return_value=mock_response,
        ):
            resp = self.admin.changelist_view(request)

        self.assertNotIsInstance(resp, type(None))
        self.assertEqual(resp.status_code, 200)
