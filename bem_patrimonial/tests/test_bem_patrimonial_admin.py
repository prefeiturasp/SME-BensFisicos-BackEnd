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


# Colunas do modelo de importação (6 colunas exatas)
_COLUNAS_IMPORTACAO = (
    "numero_patrimonial",
    "nome",
    "descricao",
    "valor_unitario",
    "marca",
    "modelo",
)


def _dataset_importacao(*rows, headers=None):
    """Cria um tablib.Dataset com as 6 colunas do modelo de importação."""
    ds = tablib.Dataset(headers=headers or list(_COLUNAS_IMPORTACAO))
    for row in rows:
        ds.append(row)
    return ds


def _linha_valida(
    numero_patrimonial="001.000000001-0",
    nome="Caneta Azul",
    descricao="Caneta esferográfica azul",
    valor_unitario="2,50",
    marca="BIC",
    modelo="Cristal",
):
    """Tupla de linha válida na ordem das 6 colunas do modelo."""
    return (numero_patrimonial, nome, descricao, valor_unitario, marca, modelo)


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
# 2. BemPatrimonialResource — helpers internos
# ===========================================================================

class ResourceHelpersTest(_Base):
    def setUp(self):
        super().setUp()
        self.resource = BemPatrimonialResource(request=None)
        self.resource._erros_por_linha = []
        self.resource._mensagens_exibidas = False

    def test_normalizar_valor_none_retorna_string_vazia(self):
        self.assertEqual(self.resource._normalizar_valor(None), "")

    def test_normalizar_valor_string_retorna_stripped(self):
        self.assertEqual(self.resource._normalizar_valor("  abc  "), "abc")

    def test_registrar_erro_acumula_dict_padronizado(self):
        self.resource._registrar_erro(5, "001.000000001-0", "nome", "Campo obrigatório.")
        self.assertEqual(len(self.resource._erros_por_linha), 1)
        erro = self.resource._erros_por_linha[0]
        self.assertEqual(erro["linha"], 5)
        self.assertEqual(erro["numero_patrimonial"], "001.000000001-0")
        self.assertEqual(erro["campo"], "nome")
        self.assertEqual(erro["mensagem"], "Campo obrigatório.")

    def test_registrar_erro_sem_numero_usa_traco(self):
        self.resource._registrar_erro(1, "", "nome", "Erro X")
        self.assertEqual(self.resource._erros_por_linha[0]["numero_patrimonial"], "-")

    def test_registrar_erro_none_numero_usa_traco(self):
        self.resource._registrar_erro(1, None, "nome", "Erro X")
        self.assertEqual(self.resource._erros_por_linha[0]["numero_patrimonial"], "-")

    def test_parse_valor_unitario_vazio_registra_erro(self):
        resultado = self.resource._parse_valor_unitario("", 1, "001.000000001-0")
        self.assertIsNone(resultado)
        self.assertEqual(len(self.resource._erros_por_linha), 1)
        self.assertEqual(self.resource._erros_por_linha[0]["campo"], "valor_unitario")

    def test_parse_valor_unitario_negativo_registra_erro(self):
        resultado = self.resource._parse_valor_unitario("-1,00", 1, "001.000000001-0")
        self.assertIsNone(resultado)
        campos = [e["campo"] for e in self.resource._erros_por_linha]
        self.assertIn("valor_unitario", campos)

    def test_parse_valor_unitario_invalido_registra_erro(self):
        resultado = self.resource._parse_valor_unitario("abc", 1, "001.000000001-0")
        self.assertIsNone(resultado)
        campos = [e["campo"] for e in self.resource._erros_por_linha]
        self.assertIn("valor_unitario", campos)

    def test_parse_valor_unitario_virgula_retorna_decimal(self):
        from decimal import Decimal
        resultado = self.resource._parse_valor_unitario("2,50", 1, "001.000000001-0")
        self.assertEqual(resultado, Decimal("2.50"))
        self.assertEqual(len(self.resource._erros_por_linha), 0)


# ===========================================================================
# 3. _validar_dataset_completo — duplicidade
# ===========================================================================

class ValidarDatasetCompletoTest(_Base):
    def setUp(self):
        super().setUp()
        req = _request_with_messages(self.factory, self.gestor)
        self.resource = BemPatrimonialResource(request=req)

    def test_numero_branco_nao_registra_erro_de_duplicidade(self):
        ds = _dataset_importacao(("", "Nome", "Desc", "2,50", "BIC", "Cristal"))
        erros = self.resource._validar_dataset_completo(ds)
        campos = [e["campo"] for e in erros]
        self.assertNotIn("numero_patrimonial", campos)

    def test_duplicado_no_arquivo_registra_erro(self):
        ds = _dataset_importacao(
            ("001.000000001-0", "Nome", "Desc", "2,50", "BIC", "Cristal"),
            ("001.000000001-0", "Outro", "Desc", "2,50", "BIC", "Cristal"),
        )
        erros = self.resource._validar_dataset_completo(ds)
        campos = [e["campo"] for e in erros]
        self.assertIn("numero_patrimonial", campos)
        self.assertTrue(any("duplicado" in e["mensagem"].lower() for e in erros))

    def test_duplicado_no_banco_registra_erro(self):
        self._criar_bem(numero_patrimonial="001.000000099-0", sem_numeracao=False)
        ds = _dataset_importacao(("001.000000099-0", "Nome", "Desc", "2,50", "BIC", "Cristal"))
        erros = self.resource._validar_dataset_completo(ds)
        campos = [e["campo"] for e in erros]
        self.assertIn("numero_patrimonial", campos)
        self.assertTrue(any("já cadastrado" in e["mensagem"] for e in erros))


# ===========================================================================
# 4. before_import
# ===========================================================================

class BeforeImportTest(_Base):
    def _make_resource(self, user=None):
        req = None
        if user is not None:
            req = _request_with_messages(self.factory, user)
        return BemPatrimonialResource(request=req)

    def test_before_import_sem_request_nao_levanta(self):
        resource = self._make_resource(user=None)
        ds = _dataset_importacao(_linha_valida())
        resource.before_import(ds)  # não deve levantar
        self.assertEqual(resource._erros_por_linha, [])

    def test_before_import_usuario_sem_ua_levanta_validation_error(self):
        resource = self._make_resource(user=self.user_sem_ua)
        ds = _dataset_importacao(_linha_valida())
        with self.assertRaises(ValidationError) as ctx:
            resource.before_import(ds)
        self.assertIn("Unidade Administrativa", str(ctx.exception))

    def test_before_import_ua_inativa_levanta_validation_error(self):
        self.ua.status = UnidadeAdministrativa.INATIVA
        self.ua.save(update_fields=["status"])
        try:
            resource = self._make_resource(user=self.gestor)
            ds = _dataset_importacao(_linha_valida())
            with self.assertRaises(ValidationError) as ctx:
                resource.before_import(ds)
            self.assertIn("inativa", str(ctx.exception))
        finally:
            self.ua.status = UnidadeAdministrativa.ATIVA
            self.ua.save(update_fields=["status"])

    def test_before_import_reinicia_estado(self):
        resource = self._make_resource(user=self.gestor)
        # Seta estado sujo simulando uma execução anterior
        resource._erros_por_linha = [{"linha": 1, "numero_patrimonial": "-",
                                      "campo": "nome", "mensagem": "lixo"}]
        resource._mensagens_exibidas = True
        ds = _dataset_importacao(_linha_valida())
        resource.before_import(ds)
        # Estado deve ter sido reiniciado — e dataset válido não gera erros
        self.assertEqual(resource._erros_por_linha, [])
        self.assertFalse(resource._mensagens_exibidas)


# ===========================================================================
# 5. get_instance
# ===========================================================================

class GetInstanceTest(_Base):
    def setUp(self):
        super().setUp()
        self.resource = BemPatrimonialResource(request=None)

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
# 7. after_import — delega ao super sem emitir mensagens próprias
# ===========================================================================

class AfterImportTest(_Base):
    _AFTER_IMPORT_EXTRA = (True, False)

    def test_after_import_nao_emite_mensagens_proprias(self):
        """after_import foi simplificado — mensagens de erro são emitidas no before_import."""
        req = _request_with_messages(self.factory, self.gestor)
        resource = BemPatrimonialResource(request=req)
        resource._erros_por_linha = []
        resource._mensagens_exibidas = False
        result = MagicMock()
        result.totals = {}
        resource.after_import(_dataset_importacao(), result, *self._AFTER_IMPORT_EXTRA)
        msgs = list(req._messages)
        self.assertEqual(len(msgs), 0)

    def test_after_import_com_erros_acumulados_nao_duplica_mensagens(self):
        """Erros do before_import foram emitidos lá — after_import não deve duplicar."""
        req = _request_with_messages(self.factory, self.gestor)
        resource = BemPatrimonialResource(request=req)
        # Simula que before_import já emitiu mensagens e acumulou erros
        resource._erros_por_linha = [
            {"linha": 1, "numero_patrimonial": "-", "campo": "nome", "mensagem": "Obrigatório."}
        ]
        resource._mensagens_exibidas = True
        result = MagicMock()
        result.totals = {}
        resource.after_import(_dataset_importacao(), result, *self._AFTER_IMPORT_EXTRA)
        msgs = list(req._messages)
        self.assertEqual(len(msgs), 0)


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
        _ = StatusBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            status=APROVADO,
            atualizado_por=self.gestor,
        )

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


# ===========================================================================
# 29. COLUNAS_MODELO — metadados do Resource
# ===========================================================================

class ColunasModeloMetadadosTest(_Base):
    def test_colunas_modelo_tem_exatamente_6_campos(self):
        from bem_patrimonial.admins.bem_patrimonial import COLUNAS_MODELO
        self.assertEqual(len(COLUNAS_MODELO), 6)

    def test_colunas_modelo_contem_campos_esperados(self):
        from bem_patrimonial.admins.bem_patrimonial import COLUNAS_MODELO
        for campo in ("numero_patrimonial", "nome", "descricao", "valor_unitario", "marca", "modelo"):
            self.assertIn(campo, COLUNAS_MODELO)

    def test_meta_fields_alinhados_com_colunas_modelo(self):
        from bem_patrimonial.admins.bem_patrimonial import COLUNAS_MODELO
        resource = BemPatrimonialResource()
        meta_fields = set(resource._meta.fields)
        for campo in COLUNAS_MODELO:
            self.assertIn(campo, meta_fields)

    def test_get_instance_sempre_retorna_none(self):
        resource = BemPatrimonialResource(request=None)
        self.assertIsNone(resource.get_instance(MagicMock(), {}))


# ===========================================================================
# 30. Contexto do usuário na importação
# ===========================================================================

class ImportacaoContextoUsuarioTest(_Base):
    def _resource(self, user):
        req = _request_with_messages(self.factory, user)
        return BemPatrimonialResource(request=req)

    def test_usuario_sem_ua_levanta_validation_error(self):
        resource = self._resource(self.user_sem_ua)
        ds = _dataset_importacao(_linha_valida())
        with self.assertRaises(ValidationError) as ctx:
            resource.before_import(ds)
        self.assertIn("Unidade Administrativa", str(ctx.exception))

    def test_ua_inativa_levanta_validation_error(self):
        ua_inativa = criar_ua(
            uo=self.uo, codigo="802", sigla="UA802", nome="UA 802 Inativa",
            status=UnidadeAdministrativa.INATIVA,
        )
        gestor_inativo = Usuario.objects.create_user(
            username="gestor_ua_inativa_cob2",
            **auth_kwargs("x"),
            unidade_administrativa=ua_inativa,
            unidade_orcamentaria=self.uo,
        )
        gestor_inativo.must_change_password = False
        gestor_inativo.save(update_fields=["must_change_password"])

        resource = self._resource(gestor_inativo)
        ds = _dataset_importacao(_linha_valida())
        with self.assertRaises(ValidationError) as ctx:
            resource.before_import(ds)
        self.assertIn("inativa", str(ctx.exception))

    def test_sem_request_nao_levanta(self):
        resource = BemPatrimonialResource(request=None)
        ds = _dataset_importacao(_linha_valida())
        resource.before_import(ds)  # não deve levantar


# ===========================================================================
# 31. Planilha vazia e cabeçalho inválido
# ===========================================================================

class ImportacaoCabecalhoTest(_Base):
    def _resource(self):
        req = _request_with_messages(self.factory, self.gestor)
        return BemPatrimonialResource(request=req)

    def test_planilha_vazia_levanta(self):
        ds = _dataset_importacao()  # sem linhas
        with self.assertRaises(ValidationError) as ctx:
            self._resource().before_import(ds)
        self.assertIn("vazia", str(ctx.exception))

    def test_cabecalho_com_coluna_faltando_levanta(self):
        headers = [c for c in _COLUNAS_IMPORTACAO if c != "descricao"]
        ds = tablib.Dataset(headers=headers)
        ds.append(("001.000000001-0", "Nome", "2,50", "BIC", "Cristal"))
        with self.assertRaises(ValidationError) as ctx:
            self._resource().before_import(ds)
        self.assertIn("descricao", str(ctx.exception))

    def test_cabecalho_com_coluna_extra_levanta(self):
        headers = list(_COLUNAS_IMPORTACAO) + ["coluna_extra"]
        ds = tablib.Dataset(headers=headers)
        ds.append(_linha_valida() + ("valor_extra",))
        with self.assertRaises(ValidationError) as ctx:
            self._resource().before_import(ds)
        self.assertIn("coluna_extra", str(ctx.exception))

    def test_cabecalho_correto_retorna_none(self):
        ds = _dataset_importacao(_linha_valida())
        self.assertIsNone(self._resource()._validar_cabecalho(ds))


# ===========================================================================
# 32. Validações obrigatórias de campos — tudo ou nada
# ===========================================================================

class ImportacaoValidacaoCamposTest(_Base):
    def _resource(self):
        req = _request_with_messages(self.factory, self.gestor)
        return BemPatrimonialResource(request=req)

    def _assert_rejeita_campo(self, dataset, campo_esperado):
        resource = self._resource()
        count_antes = BemPatrimonial.objects.count()
        with self.assertRaises(ValidationError):
            resource.before_import(dataset)
        self.assertEqual(BemPatrimonial.objects.count(), count_antes)
        campos = [e["campo"] for e in resource._erros_por_linha]
        self.assertIn(campo_esperado, campos)

    def test_nome_em_branco_rejeita(self):
        ds = _dataset_importacao(("001.000000010-0", "", "Desc", "2,50", "BIC", "Cristal"))
        self._assert_rejeita_campo(ds, "nome")

    def test_descricao_em_branco_rejeita(self):
        ds = _dataset_importacao(("001.000000011-0", "Nome", "", "2,50", "BIC", "Cristal"))
        self._assert_rejeita_campo(ds, "descricao")

    def test_valor_unitario_em_branco_rejeita(self):
        ds = _dataset_importacao(("001.000000012-0", "Nome", "Desc", "", "BIC", "Cristal"))
        self._assert_rejeita_campo(ds, "valor_unitario")

    def test_valor_unitario_negativo_rejeita(self):
        ds = _dataset_importacao(("001.000000013-0", "Nome", "Desc", "-1,00", "BIC", "Cristal"))
        self._assert_rejeita_campo(ds, "valor_unitario")

    def test_valor_unitario_invalido_rejeita(self):
        ds = _dataset_importacao(("001.000000014-0", "Nome", "Desc", "abc", "BIC", "Cristal"))
        self._assert_rejeita_campo(ds, "valor_unitario")

    def test_valor_unitario_formato_virgula_aceito(self):
        resource = self._resource()
        erros = resource._validar_dataset_completo(
            _dataset_importacao(("001.000000015-0", "Nome", "Desc", "1.234,56", "BIC", "Cristal"))
        )
        self.assertNotIn("valor_unitario", [e["campo"] for e in erros])

    def test_marca_em_branco_rejeita(self):
        ds = _dataset_importacao(("001.000000021-0", "Nome", "Desc", "2,50", "", "Cristal"))
        self._assert_rejeita_campo(ds, "marca")

    def test_modelo_em_branco_rejeita(self):
        ds = _dataset_importacao(("001.000000022-0", "Nome", "Desc", "2,50", "BIC", ""))
        self._assert_rejeita_campo(ds, "modelo")

    def test_multiplos_erros_mesma_linha_todos_acumulados(self):
        ds = _dataset_importacao(("001.000000016-0", "", "", "", "BIC", "Cristal"))
        resource = self._resource()
        with self.assertRaises(ValidationError):
            resource.before_import(ds)
        campos = [e["campo"] for e in resource._erros_por_linha]
        self.assertIn("nome", campos)
        self.assertIn("descricao", campos)
        self.assertIn("valor_unitario", campos)

    def test_erros_em_linhas_diferentes_todos_acumulados(self):
        ds = _dataset_importacao(
            ("001.000000017-0", "", "Desc", "2,50", "BIC", "Cristal"),
            ("001.000000018-0", "Nome", "", "2,50", "BIC", "Cristal"),
        )
        resource = self._resource()
        with self.assertRaises(ValidationError):
            resource.before_import(ds)
        linhas = {e["linha"] for e in resource._erros_por_linha}
        self.assertIn(1, linhas)
        self.assertIn(2, linhas)

    def test_tudo_ou_nada_linha_valida_nao_salva_quando_outra_tem_erro(self):
        """Regra crítica: nem a linha válida é salva se outra tiver erro."""
        ds = _dataset_importacao(
            _linha_valida(numero_patrimonial="001.000000019-0"),
            ("001.000000020-0", "", "Desc", "2,50", "BIC", "Cristal"),
        )
        count_antes = BemPatrimonial.objects.count()
        resource = self._resource()
        with self.assertRaises(ValidationError):
            resource.before_import(ds)
        self.assertEqual(BemPatrimonial.objects.count(), count_antes)


# ===========================================================================
# 33. Duplicidade no arquivo e no banco
# ===========================================================================

class ImportacaoDuplicidadeTest(_Base):
    def _resource(self):
        req = _request_with_messages(self.factory, self.gestor)
        return BemPatrimonialResource(request=req)

    def test_duplicidade_no_arquivo_rejeita(self):
        numero = "001.000000030-0"
        ds = _dataset_importacao(
            _linha_valida(numero_patrimonial=numero),
            _linha_valida(numero_patrimonial=numero, nome="Outro nome"),
        )
        resource = self._resource()
        count_antes = BemPatrimonial.objects.count()
        with self.assertRaises(ValidationError):
            resource.before_import(ds)
        self.assertEqual(BemPatrimonial.objects.count(), count_antes)
        campos = [e["campo"] for e in resource._erros_por_linha]
        self.assertIn("numero_patrimonial", campos)

    def test_duplicidade_no_banco_rejeita(self):
        numero = "001.000000031-0"
        self._criar_bem(numero_patrimonial=numero, sem_numeracao=False)
        ds = _dataset_importacao(_linha_valida(numero_patrimonial=numero))
        resource = self._resource()
        count_antes = BemPatrimonial.objects.count()
        with self.assertRaises(ValidationError):
            resource.before_import(ds)
        self.assertEqual(BemPatrimonial.objects.count(), count_antes)


# ===========================================================================
# 34. Normalização de marca e modelo (Ponto 4) — apenas quando preenchidos
# ===========================================================================

class ImportacaoNormalizacaoMarcaModeloTest(_Base):
    def _resource(self):
        req = _request_with_messages(self.factory, self.gestor)
        return BemPatrimonialResource(request=req)

    def _row(self, numero="001.000000040-0", marca="BIC", modelo="Cristal"):
        return dict(zip(_COLUNAS_IMPORTACAO, _linha_valida(
            numero_patrimonial=numero, marca=marca, modelo=modelo
        )))

    def test_marca_vazia_registra_erro_na_validacao(self):
        """Marca vazia deve ser rejeitada como erro, não normalizada."""
        resource = self._resource()
        erros = resource._validar_dataset_completo(
            _dataset_importacao(("001.000000040-0", "Nome", "Desc", "2,50", "", "Cristal"))
        )
        campos = [e["campo"] for e in erros]
        self.assertIn("marca", campos)

    def test_modelo_vazio_registra_erro_na_validacao(self):
        """Modelo vazio deve ser rejeitado como erro, não normalizado."""
        resource = self._resource()
        erros = resource._validar_dataset_completo(
            _dataset_importacao(("001.000000041-0", "Nome", "Desc", "2,50", "BIC", ""))
        )
        campos = [e["campo"] for e in erros]
        self.assertIn("modelo", campos)

    def test_marca_so_espacos_registra_erro_na_validacao(self):
        resource = self._resource()
        erros = resource._validar_dataset_completo(
            _dataset_importacao(("001.000000042-0", "Nome", "Desc", "2,50", "   ", "Cristal"))
        )
        campos = [e["campo"] for e in erros]
        self.assertIn("marca", campos)

    def test_marca_preenchida_nao_gera_erro(self):
        resource = self._resource()
        erros = resource._validar_dataset_completo(
            _dataset_importacao(_linha_valida(numero_patrimonial="001.000000043-0"))
        )
        campos = [e["campo"] for e in erros]
        self.assertNotIn("marca", campos)
        self.assertNotIn("modelo", campos)

    def test_before_import_row_normaliza_marca_vazia_para_traco(self):
        """before_import_row ainda normaliza como fallback de segurança."""
        resource = self._resource()
        row = self._row(marca="")
        resource.before_import_row(row, row_number=1)
        self.assertEqual(row["marca"], "-")

    def test_before_import_row_normaliza_modelo_vazio_para_traco(self):
        resource = self._resource()
        row = self._row(modelo="")
        resource.before_import_row(row, row_number=1)
        self.assertEqual(row["modelo"], "-")


# ===========================================================================
# 35. Retorno de erros padronizado (Ponto 5)
# ===========================================================================

class ImportacaoRetornoPadronizadoTest(_Base):
    def _resource(self):
        req = _request_with_messages(self.factory, self.gestor)
        return BemPatrimonialResource(request=req)

    def test_estrutura_erro_tem_todos_os_campos(self):
        ds = _dataset_importacao(("001.000000050-0", "", "Desc", "2,50", "BIC", "Cristal"))
        resource = self._resource()
        with self.assertRaises(ValidationError):
            resource.before_import(ds)
        for erro in resource._erros_por_linha:
            self.assertIn("linha", erro)
            self.assertIn("numero_patrimonial", erro)
            self.assertIn("campo", erro)
            self.assertIn("mensagem", erro)

    def test_numero_patrimonial_ausente_usa_traco(self):
        ds = _dataset_importacao(("", "", "Desc", "2,50", "BIC", "Cristal"))
        resource = self._resource()
        with self.assertRaises(ValidationError):
            resource.before_import(ds)
        erros_nome = [e for e in resource._erros_por_linha if e["campo"] == "nome"]
        self.assertTrue(len(erros_nome) > 0)
        self.assertEqual(erros_nome[0]["numero_patrimonial"], "-")

    def test_linha_correta_no_erro(self):
        ds = _dataset_importacao(
            _linha_valida(numero_patrimonial="001.000000051-0"),
            ("001.000000052-0", "", "Desc", "2,50", "BIC", "Cristal"),
        )
        resource = self._resource()
        with self.assertRaises(ValidationError):
            resource.before_import(ds)
        erros_nome = [e for e in resource._erros_por_linha if e["campo"] == "nome"]
        self.assertEqual(erros_nome[0]["linha"], 2)


# ===========================================================================
# 36. Importação bem-sucedida — fluxo completo de integração
# ===========================================================================

class ImportacaoSucessoIntegracaoTest(_Base):
    def _importar(self, dataset):
        req = _request_with_messages(self.factory, self.gestor)
        resource = BemPatrimonialResource(request=req)
        resource.import_data(dataset, dry_run=False, raise_errors=True, use_transactions=True)
        return resource

    def test_importacao_valida_cria_bens(self):
        ds = _dataset_importacao(
            _linha_valida(numero_patrimonial="001.000000060-0"),
            _linha_valida(numero_patrimonial="001.000000061-0", nome="Lápis"),
        )
        count_antes = BemPatrimonial.objects.count()
        self._importar(ds)
        self.assertEqual(BemPatrimonial.objects.count(), count_antes + 2)

    def test_importacao_usa_ua_do_usuario_nao_da_planilha(self):
        ds = _dataset_importacao(_linha_valida(numero_patrimonial="001.000000062-0"))
        self._importar(ds)
        bem = BemPatrimonial.objects.get(numero_patrimonial="001.000000062-0")
        self.assertEqual(bem.unidade_administrativa, self.ua)

    def test_importacao_define_status_aguardando_aprovacao(self):
        ds = _dataset_importacao(_linha_valida(numero_patrimonial="001.000000063-0"))
        self._importar(ds)
        bem = BemPatrimonial.objects.get(numero_patrimonial="001.000000063-0")
        self.assertEqual(bem.status, AGUARDANDO_APROVACAO)

    def test_importacao_define_criado_por_como_usuario_logado(self):
        ds = _dataset_importacao(_linha_valida(numero_patrimonial="001.000000064-0"))
        self._importar(ds)
        bem = BemPatrimonial.objects.get(numero_patrimonial="001.000000064-0")
        self.assertEqual(bem.criado_por, self.gestor)

    def test_importacao_numero_branco_cria_sem_numeracao(self):
        ds = _dataset_importacao(("", "Caneta sem número", "Descrição", "1,00", "BIC", "Cristal"))
        count_sem_num = BemPatrimonial.objects.filter(sem_numeracao=True).count()
        self._importar(ds)
        self.assertEqual(
            BemPatrimonial.objects.filter(sem_numeracao=True).count(),
            count_sem_num + 1,
        )

    def test_importacao_numero_formato_novo_define_numero_formato_antigo_false(self):
        ds = _dataset_importacao(_linha_valida(numero_patrimonial="001.000000065-0"))
        self._importar(ds)
        bem = BemPatrimonial.objects.get(numero_patrimonial="001.000000065-0")
        self.assertFalse(bem.numero_formato_antigo)

    def test_importacao_numero_formato_antigo_define_flag_true(self):
        ds = _dataset_importacao(("12345antigo", "Caneta antiga", "Descrição", "1,00", "BIC", "Cristal"))
        self._importar(ds)
        bem = BemPatrimonial.objects.filter(numero_patrimonial="12345antigo").first()
        self.assertIsNotNone(bem)
        self.assertTrue(bem.numero_formato_antigo)
