# Cobertura do bem_patrimonial/admins/bem_patrimonial.py
# Complementa tests_admin.py, tests_aprovacao_lote.py, tests_admin_list_display.py,
# test_edicao_restrita_operador.py e tests_export_pdf.py

import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, RequestFactory, Client
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpResponseRedirect
from django.urls import reverse

from bem_patrimonial.models import BemPatrimonial, StatusBemPatrimonial
from bem_patrimonial.admins.bem_patrimonial import (
    BemPatrimonialAdmin,
    HistoricoGeralInline,
    aprovar_bens,
    reprovar_bens,
)
from bem_patrimonial.constants import (
    AGUARDANDO_APROVACAO,
    APROVADO,
    BAIXA_FISICA,
    NAO_APROVADO,
)
from bem_patrimonial.formats import PDFFormat
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


def _request_with_messages(factory, user, method="GET", path="/admin/"):
    request = factory.get(path) if method == "GET" else factory.post(path)
    request.user = user
    setattr(request, "session", "session")
    setattr(request, "_messages", FallbackStorage(request))
    return request


class BemPatrimonialAdminCoberturaTest(TestCase):
    """Testes para cobrir 100% do bem_patrimonial/admins/bem_patrimonial.py."""

    @classmethod
    def setUpTestData(cls):
        cls.uo = criar_uo(codigo="100", nome="UO 100")
        cls.ua = criar_ua(
            uo=cls.uo,
            codigo="001",
            sigla="UA",
            nome="UA Teste",
            status=UnidadeAdministrativa.ATIVA,
        )
        cls.grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        cls.grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)

        cls.gestor = Usuario.objects.create_user(
            username="gestor_cob",
            password="x",
            unidade_administrativa=cls.ua,
            unidade_orcamentaria=cls.uo,
            is_staff=True,
        )
        cls.gestor.must_change_password = False
        cls.gestor.save(update_fields=["must_change_password"])
        cls.gestor.groups.add(cls.grupo_gestor)

        cls.operador = Usuario.objects.create_user(
            username="operador_cob",
            password="x",
            unidade_administrativa=cls.ua,
            unidade_orcamentaria=cls.uo,
            is_staff=True,
        )
        cls.operador.groups.add(cls.grupo_operador)

        cls.user_sem_grupo = Usuario.objects.create_user(
            username="sem_grupo_cob",
            password="x",
            unidade_administrativa=cls.ua,
            unidade_orcamentaria=cls.uo,
            is_staff=True,
        )
        User = get_user_model()
        cls.superuser = User.objects.create_superuser(
            username="super_cob",
            email="super@test.com",
            password="x",
        )
        cls.superuser.unidade_orcamentaria = cls.uo
        cls.superuser.must_change_password = False
        cls.superuser.save(update_fields=["unidade_orcamentaria", "must_change_password"])
        cls.superuser.groups.add(cls.grupo_gestor)

    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = BemPatrimonialAdmin(BemPatrimonial, self.site)
        # Permissão de adicionar bem patrimonial para o gestor (evita 403 no add_view)
        ct = ContentType.objects.get_for_model(BemPatrimonial)
        add_perm, _ = Permission.objects.get_or_create(
            codename="add_bempatrimonial",
            content_type=ct,
            defaults={"name": "Add bem patrimonial"},
        )
        self.gestor.user_permissions.add(add_perm)
        # Limpa caches de permissão para evitar 403 por _perm_cache desatualizado
        for attr in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
            if hasattr(self.gestor, attr):
                delattr(self.gestor, attr)

    def _criar_bem(self, **kwargs):
        defaults = {
            "nome": "Bem",
            "descricao": "D",
            "valor_unitario": 1,
            "marca": "M",
            "modelo": "X",
            "numero_processo": "P1",
            "unidade_administrativa": self.ua,
            "criado_por": self.gestor,
            "status": APROVADO,
            "sem_numeracao": True,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    # --- get_actions: delete_selected removido ---
    def test_get_actions_remove_delete_selected(self):
        request = _request_with_messages(self.factory, self.gestor)
        actions = self.admin.get_actions(request)
        self.assertNotIn("delete_selected", actions)

    # --- delete_view ---
    def test_delete_view_obj_none_redirect_changelist(self):
        request = _request_with_messages(self.factory, self.gestor)
        with patch.object(self.admin, "get_object", return_value=None):
            resp = self.admin.delete_view(request, "999999", None)
        self.assertIsInstance(resp, HttpResponseRedirect)
        self.assertIn("bempatrimonial", resp.url)

    def test_delete_view_sem_permissao_raise_permission_denied(self):
        bem = self._criar_bem()
        request = _request_with_messages(self.factory, self.operador)
        request.resolver_match = MagicMock()
        request.resolver_match.url_name = "bempatrimonial_delete"
        with self.assertRaises(PermissionDenied):
            self.admin.delete_view(request, str(bem.pk), None)

    def test_delete_view_post_deleta_e_redireciona(self):
        bem = self._criar_bem()
        request = _request_with_messages(self.factory, self.gestor, method="POST")
        request.resolver_match = MagicMock()
        request.resolver_match.url_name = "bempatrimonial_delete"
        request._body = b""
        resp = self.admin.delete_view(request, str(bem.pk), None)
        self.assertIsInstance(resp, HttpResponseRedirect)
        self.assertFalse(BemPatrimonial.objects.filter(pk=bem.pk).exists())

    def test_delete_view_get_retorna_template_confirmacao(self):
        bem = self._criar_bem()
        request = _request_with_messages(self.factory, self.gestor)
        request.resolver_match = MagicMock()
        request.resolver_match.url_name = "bempatrimonial_delete"
        resp = self.admin.delete_view(request, str(bem.pk), None)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("object", resp.context_data)

    # --- get_readonly_fields: obj None; user nem gestor nem operador ---
    def test_get_readonly_fields_obj_none_retorna_base(self):
        request = _request_with_messages(self.factory, self.gestor)
        r = self.admin.get_readonly_fields(request, obj=None)
        self.assertEqual(r, ("status", "criado_por", "criado_em"))

    def test_get_readonly_fields_usuario_sem_grupo_retorna_base_mais_campos(self):
        request = _request_with_messages(self.factory, self.user_sem_grupo)
        bem = self._criar_bem()
        r = self.admin.get_readonly_fields(request, obj=bem)
        self.assertIn("unidade_administrativa", r)
        self.assertIn("localizacao", r)
        self.assertIn("nome", r)

    # --- get_fields: com obj remove cadastro_modo ---
    def test_get_fields_com_obj_nao_tem_cadastro_modo(self):
        request = _request_with_messages(self.factory, self.gestor)
        bem = self._criar_bem()
        fields = self.admin.get_fields(request, obj=bem)
        flat = [f for f in fields if isinstance(f, str)]
        self.assertNotIn("cadastro_modo", flat)

    def test_get_fields_sem_obj_tem_cadastro_modo(self):
        request = _request_with_messages(self.factory, self.gestor)
        fields = self.admin.get_fields(request, obj=None)
        flat = [f for f in fields if isinstance(f, str)]
        self.assertIn("cadastro_modo", flat)

    # --- has_change_permission: excluido, BAIXA_FISICA ---
    def test_has_change_permission_false_se_excluido(self):
        request = _request_with_messages(self.factory, self.gestor)
        bem = self._criar_bem()
        bem.excluido = True
        self.assertFalse(self.admin.has_change_permission(request, obj=bem))

    def test_has_change_permission_false_se_baixa_fisica(self):
        request = _request_with_messages(self.factory, self.gestor)
        bem = self._criar_bem(status=BAIXA_FISICA)
        self.assertFalse(self.admin.has_change_permission(request, obj=bem))

    # --- has_delete_permission ---
    def test_has_delete_permission_false_se_obj_none(self):
        request = _request_with_messages(self.factory, self.gestor)
        self.assertFalse(self.admin.has_delete_permission(request, obj=None))

    def test_has_delete_permission_false_se_excluido(self):
        request = _request_with_messages(self.factory, self.gestor)
        bem = self._criar_bem()
        bem.excluido = True
        self.assertFalse(self.admin.has_delete_permission(request, obj=bem))

    def test_has_delete_permission_false_operador(self):
        request = _request_with_messages(self.factory, self.operador)
        bem = self._criar_bem()
        self.assertFalse(self.admin.has_delete_permission(request, obj=bem))

    def test_has_delete_permission_false_se_baixa_fisica(self):
        request = _request_with_messages(self.factory, self.gestor)
        bem = self._criar_bem(status=BAIXA_FISICA)
        self.assertFalse(self.admin.has_delete_permission(request, obj=bem))

    def test_has_delete_permission_true_gestor_bem_normal(self):
        request = _request_with_messages(self.factory, self.gestor)
        bem = self._criar_bem()
        self.assertTrue(self.admin.has_delete_permission(request, obj=bem))

    # --- save_model: BAIXA_FISICA em edição; IntegrityError numero_patrimonial ---
    def test_save_model_raise_se_editar_bem_baixa_fisica(self):
        bem = self._criar_bem(status=BAIXA_FISICA)
        request = _request_with_messages(self.factory, self.gestor, method="POST")
        form = MagicMock()
        form.cleaned_data = {}
        with self.assertRaises(ValidationError) as ctx:
            self.admin.save_model(request, bem, form, change=True)
        self.assertIn("Baixa Física", str(ctx.exception))

    def test_save_model_criar_preenche_criado_por_e_status_default(self):
        bem = BemPatrimonial(
            nome="Novo",
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
        self.admin.save_model(request, bem, form, change=False)
        self.assertEqual(bem.criado_por, self.gestor)
        self.assertEqual(bem.status, AGUARDANDO_APROVACAO)

    def test_save_model_integrity_error_numero_patrimonial_validation_error(self):
        self._criar_bem(numero_patrimonial="000.000000001-0", sem_numeracao=False)
        bem = BemPatrimonial(
            nome="Outro",
            descricao="D",
            valor_unitario=1,
            marca="M",
            modelo="X",
            numero_processo="P",
            unidade_administrativa=self.ua,
            criado_por=self.gestor,
            numero_patrimonial="000.000000001-0",
            sem_numeracao=False,
        )
        request = _request_with_messages(self.factory, self.gestor, method="POST")
        form = MagicMock()
        form.cleaned_data = {}
        with self.assertRaises(ValidationError) as ctx:
            self.admin.save_model(request, bem, form, change=False)
        self.assertIn("numero_patrimonial", str(ctx.exception).lower())

    # --- get_export_formats, get_resource_kwargs ---
    def test_get_export_formats_retorna_lista_com_pdf(self):
        formats = self.admin.get_export_formats()
        self.assertIn(PDFFormat, formats)

    def test_get_resource_kwargs_inclui_request(self):
        request = _request_with_messages(self.factory, self.gestor)
        rk = self.admin.get_resource_kwargs(request)
        self.assertEqual(rk.get("request"), request)

    def test_get_export_data_pdf_format_atribui_request_e_queryset(self):
        request = _request_with_messages(self.factory, self.gestor)
        qs = BemPatrimonial.objects.none()
        fmt = PDFFormat()
        self.admin.get_export_data(fmt, qs, request=request)
        self.assertEqual(getattr(fmt, "_export_request", None), request)
        self.assertEqual(getattr(fmt, "_export_queryset", None), qs)

    # --- save_formset / save_status (branch StatusBemPatrimonial) ---
    def test_save_formset_status_chama_save_status(self):
        request = _request_with_messages(self.factory, self.gestor, method="POST")
        form = MagicMock()
        formset = MagicMock()
        formset.model = StatusBemPatrimonial
        formset.save = MagicMock(return_value=[])
        formset.deleted_objects = []
        formset.save_m2m = MagicMock()
        self.admin.save_formset(request, form, formset, change=True)
        formset.save.assert_called()

    # --- HistoricoGeralInline (segundo arg é admin_site, não ModelAdmin) ---
    def test_historico_geral_inline_has_view_or_change_permission_true(self):
        request = _request_with_messages(self.factory, self.gestor)
        inline = HistoricoGeralInline(BemPatrimonial, self.site)
        self.assertTrue(inline.has_view_or_change_permission(request, None))

    def test_historico_geral_inline_has_add_permission_false(self):
        request = _request_with_messages(self.factory, self.gestor)
        inline = HistoricoGeralInline(BemPatrimonial, self.site)
        self.assertFalse(inline.has_add_permission(request, None))

    # --- get_inline_instances: obj None -> [] ---
    def test_get_inline_instances_obj_none_retorna_lista_vazia(self):
        request = _request_with_messages(self.factory, self.gestor)
        inlines = self.admin.get_inline_instances(request, obj=None)
        self.assertEqual(inlines, [])

    # --- alterado_em_ultimo, alterado_por_ultimo ---
    def test_alterado_em_ultimo_retorna_audit_last_at(self):
        bem = self._criar_bem()
        self.assertEqual(self.admin.alterado_em_ultimo(bem), getattr(bem, "audit_last_at", None))

    def test_alterado_por_ultimo_retorna_traco_se_sem_user_id(self):
        bem = self._criar_bem()
        self.assertEqual(self.admin.alterado_por_ultimo(bem), "—")

    def test_alterado_por_ultimo_retorna_traco_se_user_nao_existe(self):
        bem = self._criar_bem()
        bem.audit_last_by_id = 999999999
        self.assertEqual(self.admin.alterado_por_ultimo(bem), "—")

    # --- thumb, foto_preview ---
    def test_thumb_sem_foto_retorna_traco(self):
        bem = self._criar_bem()
        self.assertEqual(self.admin.thumb(bem), "—")

    def test_foto_preview_sem_foto_retorna_traco(self):
        bem = self._criar_bem()
        self.assertEqual(self.admin.foto_preview(bem), "—")

    # --- get_search_results: autocomplete ua_origem e exclude_bens ---
    def test_get_search_results_autocomplete_sem_ua_origem_retorna_none(self):
        request = self.factory.get(
            "/admin/",
            {"app_label": "bem_patrimonial", "model_name": "baixafisicabensitem", "field_name": "bem"},
        )
        request.path = "/admin/bem_patrimonial/bempatrimonial/autocomplete/"
        request.user = self.gestor
        qs = BemPatrimonial.objects.all()
        result_qs, _ = self.admin.get_search_results(request, qs, "")
        self.assertEqual(list(result_qs), [])

    def test_get_search_results_autocomplete_com_ua_origem_filtra_aprovado_e_ua(self):
        bem = self._criar_bem(status=APROVADO)
        request = self.factory.get(
            "/admin/",
            {
                "app_label": "bem_patrimonial",
                "model_name": "baixafisicabensitem",
                "field_name": "bem",
                "ua_origem": str(self.ua.pk),
            },
        )
        request.path = "/admin/bem_patrimonial/bempatrimonial/autocomplete/"
        request.user = self.gestor
        qs = BemPatrimonial.objects.filter(pk=bem.pk)
        result_qs, _ = self.admin.get_search_results(request, qs, "")
        self.assertIn(bem, result_qs)

    def test_get_search_results_autocomplete_exclude_bens_exclui_ids(self):
        b1 = self._criar_bem(status=APROVADO)
        b2 = self._criar_bem(status=APROVADO)
        request = self.factory.get(
            "/admin/",
            {
                "app_label": "bem_patrimonial",
                "model_name": "baixafisicabensitem",
                "field_name": "bem",
                "ua_origem": str(self.ua.pk),
                "exclude_bens": f"{b1.pk}",
            },
        )
        request.path = "/admin/bem_patrimonial/bempatrimonial/autocomplete/"
        request.user = self.gestor
        qs = BemPatrimonial.objects.filter(pk__in=[b1.pk, b2.pk])
        result_qs, _ = self.admin.get_search_results(request, qs, "")
        self.assertNotIn(b1, result_qs)
        self.assertIn(b2, result_qs)

    # --- add_view modo multi: linhas vazias; sucesso (Client + gestor com UA no escopo) ---
    def test_add_view_multi_linhas_vazias_retorna_super_com_erro(self):
        url = reverse("admin:bem_patrimonial_bempatrimonial_add")
        client = Client()
        client.force_login(self.gestor)
        initial_count = BemPatrimonial.objects.count()
        resp = client.post(
            url,
            data={
                "cadastro_modo": "multi",
                "multi_payload": "[]",
                "unidade_administrativa": str(self.ua.pk),
                "nome": "Nome",
                "descricao": "Desc",
                "valor_unitario": "1",
                "marca": "M",
                "modelo": "X",
                "numero_processo": "P",
            },
        )
        # Form reexibido com erro (200) ou redirect; o importante é não criar bens
        self.assertIn(resp.status_code, (200, 302))
        self.assertEqual(BemPatrimonial.objects.count(), initial_count)

    # --- render_change_form: injeta anchor (context precisa de inline_admin_formsets) ---
    def test_render_change_form_injeta_multi_anchor(self):
        request = _request_with_messages(self.factory, self.gestor)
        request.POST = request.POST.copy()
        context = {"object_id": "1", "inline_admin_formsets": []}

        # Não montamos um contexto completo de change_form (adminform, etc.).
        # Para cobrir o método e validar a injeção do anchor, mockamos o super().
        mock_super_response = MagicMock()
        mock_super_response.rendered_content = "</form>"
        mock_super_response.charset = "utf-8"
        mock_super_response.content = b""

        with patch(
            "import_export.admin.ImportExportModelAdmin.render_change_form",
            return_value=mock_super_response,
        ):
            resp = self.admin.render_change_form(request, context, add=True, change=False)
        self.assertIsNotNone(resp)
        # O admin injeta o anchor em response.content, não em rendered_content
        content = resp.content if hasattr(resp.content, "decode") else getattr(resp, "rendered_content", b"")
        if isinstance(content, str):
            content = content.encode("utf-8")
        self.assertIn(b"multi-inline-root", content)

    # --- aprovar_bens / reprovar_bens: ramo except ---
    def test_aprovar_bens_exception_mensagem_erro(self):
        bem = self._criar_bem(status=AGUARDANDO_APROVACAO)
        request = _request_with_messages(self.factory, self.gestor, method="POST")
        with patch.object(BemPatrimonial, "save", side_effect=RuntimeError("erro teste")):
            aprovar_bens(self.admin, request, BemPatrimonial.objects.filter(pk=bem.pk))
        msgs = [str(m) for m in request._messages]
        self.assertTrue(any("Erro ao aprovar" in m for m in msgs))

    def test_reprovar_bens_exception_mensagem_erro(self):
        bem = self._criar_bem(status=AGUARDANDO_APROVACAO)
        request = _request_with_messages(self.factory, self.gestor, method="POST")
        with patch.object(BemPatrimonial, "save", side_effect=RuntimeError("erro teste")):
            reprovar_bens(self.admin, request, BemPatrimonial.objects.filter(pk=bem.pk))
        msgs = [str(m) for m in request._messages]
        self.assertTrue(any("Erro ao reprovar" in m for m in msgs))
