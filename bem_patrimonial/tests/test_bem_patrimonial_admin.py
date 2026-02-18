from unittest.mock import patch, MagicMock
import json

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.test import RequestFactory, TestCase
from django.urls import reverse

from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO

from bem_patrimonial import constants
from bem_patrimonial.models import BemPatrimonial, StatusBemPatrimonial
from bem_patrimonial.admins.bem_patrimonial import (
    BemPatrimonialAdmin,
    HistoricoGeralInline,
    StatusBemPatrimonialInline,
    aprovar_bens,
    reprovar_bens,
)
from bem_patrimonial.admins.filters.bem_patrimonial_filters import SemNumeroFilter
from bem_patrimonial.admins.filters.baixados_periodo_filter import (
    BaixadosMaisDeUmPeriodoFilter,
)
from bem_patrimonial.formats import PDFFormat


User = get_user_model()


def _request_com_mensagens(factory, user, method="get"):
    request = getattr(factory, method)("/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


class AdminTestBase(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.uo = criar_uo()
        self.ua = criar_ua(uo=self.uo, status=UnidadeAdministrativa.ATIVA)
        self.grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)

        self.gestor = User.objects.create_user(
            username="gestor_bp",
            password="x",
            email="gestor@test.com",
            is_staff=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.gestor.groups.add(self.grupo_gestor)

        self.operador = User.objects.create_user(
            username="operador_bp",
            password="x",
            email="operador@test.com",
            is_staff=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.operador.groups.add(self.grupo_operador)

        self.usuario_comum = User.objects.create_user(
            username="comum_bp",
            password="x",
            email="comum@test.com",
            is_staff=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )

        self.admin = BemPatrimonialAdmin(BemPatrimonial, self.site)

    def _mk_bem(self, **kwargs):
        defaults = {
            "nome": "Bem Teste",
            "descricao": "Desc",
            "valor_unitario": 100,
            "marca": "M",
            "modelo": "X",
            "numero_processo": "PROC-1",
            "unidade_administrativa": self.ua,
            "criado_por": self.gestor,
            "status": constants.APROVADO,
            "sem_numeracao": True,
            "numero_patrimonial": None,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)


# --- Filtros ---
class TestSemNumeroFilter(AdminTestBase):
    def test_lookups(self):
        filtro = SemNumeroFilter(None, {}, BemPatrimonial, self.admin)
        request = self.factory.get("/")
        lookups = filtro.lookups(request, self.admin)
        self.assertEqual(lookups, (("1", "Somente bens sem número"),))

    def test_queryset_sem_value(self):
        self._mk_bem(numero_patrimonial="001.000000001-1")
        filtro = SemNumeroFilter(None, {}, BemPatrimonial, self.admin)
        qs = BemPatrimonial.objects.all()
        result = filtro.queryset(self.factory.get("/"), qs)
        self.assertEqual(result.count(), 1)

    def test_queryset_com_value(self):
        self._mk_bem(sem_numeracao=True, numero_patrimonial=None)
        self._mk_bem(numero_patrimonial="001.000000002-2", sem_numeracao=False)
        request = self.factory.get("/", {"sem_numero": "1"})
        params = {"sem_numero": "1"}
        filtro = SemNumeroFilter(request, params, BemPatrimonial, self.admin)
        qs = BemPatrimonial.objects.all()
        result = filtro.queryset(request, qs)
        self.assertEqual(result.count(), 1)
        self.assertTrue(result.first().sem_numeracao)


class TestBaixadosMaisDeUmPeriodoFilter(AdminTestBase):
    def test_lookups(self):
        filtro = BaixadosMaisDeUmPeriodoFilter(None, {}, BemPatrimonial, self.admin)
        request = self.factory.get("/")
        lookups = filtro.lookups(request, self.admin)
        self.assertEqual(len(lookups), 2)

    def test_queryset_sem_value(self):
        filtro = BaixadosMaisDeUmPeriodoFilter(None, {}, BemPatrimonial, self.admin)
        qs = BemPatrimonial.objects.all()
        result = filtro.queryset(self.factory.get("/"), qs)
        self.assertEqual(result.count(), qs.count())

    def test_queryset_com_value_0(self):
        request = self.factory.get("/", {"baixados_mais_de_um_periodo": "0"})
        request.user = self.gestor
        request.resolver_match = MagicMock()
        request.resolver_match.url_name = "bempatrimonial_changelist"
        qs = self.admin.get_queryset(request)
        params = {"baixados_mais_de_um_periodo": "0"}
        filtro = BaixadosMaisDeUmPeriodoFilter(request, params, BemPatrimonial, self.admin)
        result = filtro.queryset(request, qs)
        self.assertIsNotNone(result)


class TestStatusBemPatrimonialInline(AdminTestBase):
    def test_extra_zero(self):
        inline = StatusBemPatrimonialInline(BemPatrimonial, self.site)
        self.assertEqual(inline.extra, 0)


class TestHistoricoGeralInline(AdminTestBase):
    def test_has_add_permission_false(self):
        inline = HistoricoGeralInline(BemPatrimonial, self.site)
        request = self.factory.get("/")
        request.user = self.gestor
        self.assertFalse(inline.has_add_permission(request, None))

    def test_has_view_or_change_permission_true(self):
        inline = HistoricoGeralInline(BemPatrimonial, self.site)
        request = self.factory.get("/")
        request.user = self.gestor
        self.assertTrue(inline.has_view_or_change_permission(request, None))


class TestAprovarReprovarBens(AdminTestBase):
    def test_aprovar_bens_sem_permissao(self):
        self._mk_bem(status=constants.AGUARDANDO_APROVACAO)
        request = _request_com_mensagens(self.factory, self.usuario_comum)
        qs = BemPatrimonial.objects.filter(status=constants.AGUARDANDO_APROVACAO)
        aprovar_bens(self.admin, request, qs)
        self.assertEqual(BemPatrimonial.objects.filter(status=constants.APROVADO).count(), 0)

    def test_reprovar_bens_sem_permissao(self):
        self._mk_bem(status=constants.AGUARDANDO_APROVACAO)
        request = _request_com_mensagens(self.factory, self.usuario_comum)
        qs = BemPatrimonial.objects.filter(status=constants.AGUARDANDO_APROVACAO)
        reprovar_bens(self.admin, request, qs)
        self.assertEqual(BemPatrimonial.objects.filter(status=constants.NAO_APROVADO).count(), 0)


class TestBemPatrimonialAdminGetActions(AdminTestBase):
    def test_get_actions_gestor_tem_aprovar_reprovar(self):
        request = self.factory.get("/")
        request.user = self.gestor
        actions = self.admin.get_actions(request)
        self.assertIn("aprovar_bens", actions)
        self.assertIn("reprovar_bens", actions)
        self.assertNotIn("delete_selected", actions)

    def test_get_actions_nao_gestor_sem_aprovar_reprovar(self):
        request = self.factory.get("/")
        request.user = self.usuario_comum
        actions = self.admin.get_actions(request)
        self.assertNotIn("aprovar_bens", actions)
        self.assertNotIn("reprovar_bens", actions)
        self.assertNotIn("delete_selected", actions)


class TestBemPatrimonialAdminListDisplay(AdminTestBase):
    def test_get_list_display_operador_nao_gestor(self):
        request = self.factory.get("/")
        request.user = self.operador
        display = self.admin.get_list_display(request)
        self.assertEqual(display, ("numero_patrimonial", "nome", "status"))

    def test_get_list_display_gestor(self):
        request = self.factory.get("/")
        request.user = self.gestor
        display = self.admin.get_list_display(request)
        self.assertIn("unidade_administrativa", display)


class TestBemPatrimonialAdminReadonlyFields(AdminTestBase):
    def test_get_readonly_fields_sem_obj(self):
        request = self.factory.get("/")
        request.user = self.gestor
        fields = self.admin.get_readonly_fields(request, None)
        self.assertIn("status", fields)

    def test_get_readonly_fields_gestor_com_obj(self):
        bem = self._mk_bem()
        request = self.factory.get("/")
        request.user = self.gestor
        fields = self.admin.get_readonly_fields(request, bem)
        self.assertIn("status", fields)

    def test_get_readonly_fields_operador_com_obj(self):
        bem = self._mk_bem()
        request = self.factory.get("/")
        request.user = self.operador
        fields = self.admin.get_readonly_fields(request, bem)
        self.assertIn("numero_patrimonial", fields)
        self.assertIn("unidade_administrativa", fields)

    def test_get_readonly_fields_usuario_comum_com_obj(self):
        bem = self._mk_bem()
        request = self.factory.get("/")
        request.user = self.usuario_comum
        fields = self.admin.get_readonly_fields(request, bem)
        self.assertIn("unidade_administrativa", fields)


class TestBemPatrimonialAdminFields(AdminTestBase):
    def test_get_fields_sem_obj(self):
        request = self.factory.get("/")
        request.user = self.gestor
        fields = self.admin.get_fields(request, None)
        self.assertIn("cadastro_modo", [f if isinstance(f, str) else f[0] for f in fields])

    def test_get_fields_com_obj(self):
        bem = self._mk_bem()
        request = self.factory.get("/")
        request.user = self.gestor
        fields = self.admin.get_fields(request, bem)
        flat = [f if isinstance(f, str) else f[0] for f in fields]
        self.assertNotIn("cadastro_modo", flat)


class TestBemPatrimonialAdminPermissions(AdminTestBase):
    def test_has_change_permission_obj_excluido(self):
        bem = self._mk_bem()
        bem.excluido = True
        request = self.factory.get("/")
        request.user = self.gestor
        self.assertFalse(self.admin.has_change_permission(request, bem))

    def test_has_change_permission_obj_baixa_fisica(self):
        bem = self._mk_bem(status=constants.BAIXA_FISICA)
        request = self.factory.get("/")
        request.user = self.gestor
        self.assertFalse(self.admin.has_change_permission(request, bem))

    def test_has_delete_permission_sem_obj(self):
        request = self.factory.get("/")
        request.user = self.gestor
        self.assertFalse(self.admin.has_delete_permission(request, None))

    def test_has_delete_permission_obj_excluido(self):
        bem = self._mk_bem()
        bem.excluido = True
        request = self.factory.get("/")
        request.user = self.gestor
        self.assertFalse(self.admin.has_delete_permission(request, bem))

    def test_has_delete_permission_nao_gestor(self):
        bem = self._mk_bem()
        request = self.factory.get("/")
        request.user = self.usuario_comum
        self.assertFalse(self.admin.has_delete_permission(request, bem))

    def test_has_delete_permission_gestor_baixa_fisica(self):
        bem = self._mk_bem(status=constants.BAIXA_FISICA)
        request = self.factory.get("/")
        request.user = self.gestor
        self.assertFalse(self.admin.has_delete_permission(request, bem))


class TestBemPatrimonialAdminSaveModel(AdminTestBase):
    def test_save_model_novo_obj(self):
        request = _request_com_mensagens(self.factory, self.gestor, "post")
        bem = BemPatrimonial(
            nome="Novo",
            descricao="D",
            valor_unitario=10,
            unidade_administrativa=self.ua,
            status=constants.AGUARDANDO_APROVACAO,
        )
        form = MagicMock()
        self.admin.save_model(request, bem, form, change=False)
        self.assertEqual(bem.criado_por, self.gestor)
        bem.refresh_from_db()
        self.assertIsNotNone(bem.pk)

    def test_save_model_change_original_baixa_fisica(self):
        bem = self._mk_bem(status=constants.BAIXA_FISICA)
        request = _request_com_mensagens(self.factory, self.gestor, "post")
        form = MagicMock()
        with self.assertRaises(ValidationError):
            self.admin.save_model(request, bem, form, change=True)


class TestBemPatrimonialAdminDeleteView(AdminTestBase):
    def test_delete_view_obj_nao_encontrado(self):
        request = _request_com_mensagens(self.factory, self.gestor, "get")
        request.resolver_match = MagicMock()
        request.resolver_match.url_name = "bempatrimonial_delete"
        resp = self.admin.delete_view(request, 99999)
        self.assertIsInstance(resp, HttpResponseRedirect)

    def test_delete_view_get_retorna_template(self):
        bem = self._mk_bem()
        request = _request_com_mensagens(self.factory, self.gestor, "get")
        request.resolver_match = MagicMock()
        resp = self.admin.delete_view(request, str(bem.pk))
        self.assertEqual(resp.status_code, 200)

    def test_delete_view_post_deleta_e_redireciona(self):
        bem = self._mk_bem()
        pk = bem.pk
        request = _request_com_mensagens(self.factory, self.gestor, "post")
        request.META["REQUEST_METHOD"] = "POST"
        request.resolver_match = MagicMock()
        with patch.object(self.admin, "get_object", return_value=bem):
            resp = self.admin.delete_view(request, str(pk))
        self.assertIsInstance(resp, HttpResponseRedirect)
        self.assertFalse(BemPatrimonial.objects.filter(pk=pk).exists())


class TestBemPatrimonialAdminQueryset(AdminTestBase):
    def test_get_queryset_retorna_queryset_filtrado(self):
        self._mk_bem()
        request = self.factory.get("/")
        request.user = self.gestor
        request.resolver_match = MagicMock()
        request.resolver_match.url_name = "bempatrimonial_changelist"
        qs = self.admin.get_queryset(request)
        self.assertGreaterEqual(qs.count(), 1)
        self.assertTrue(hasattr(qs, "query"))


class TestBemPatrimonialAdminExport(AdminTestBase):
    def test_get_export_formats(self):
        formats = self.admin.get_export_formats()
        self.assertIn(PDFFormat, formats)

    def test_get_resource_kwargs(self):
        request = self.factory.get("/")
        request.user = self.gestor
        kwargs = self.admin.get_resource_kwargs(request)
        self.assertEqual(kwargs.get("request"), request)

    def test_get_export_data_pdf_format(self):
        self._mk_bem()
        request = self.factory.get("/")
        request.user = self.gestor
        qs = BemPatrimonial.objects.filter(unidade_administrativa=self.ua)
        pdf_format = PDFFormat()
        result = self.admin.get_export_data(pdf_format, qs, request=request)
        self.assertEqual(getattr(pdf_format, "_export_request", None), request)
        self.assertEqual(getattr(pdf_format, "_export_queryset", None), qs)


class TestBemPatrimonialAdminDisplayMethods(AdminTestBase):
    def test_alterado_em_ultimo(self):
        bem = self._mk_bem()
        bem.audit_last_at = None
        result = self.admin.alterado_em_ultimo(bem)
        self.assertIsNone(result)

    def test_alterado_por_ultimo_sem_user(self):
        bem = self._mk_bem()
        bem.audit_last_by_id = None
        result = self.admin.alterado_por_ultimo(bem)
        self.assertEqual(result, "—")

    def test_alterado_por_ultimo_com_user(self):
        bem = self._mk_bem()
        bem.audit_last_by_id = self.gestor.pk
        result = self.admin.alterado_por_ultimo(bem)
        self.assertIn(self.gestor.username, result or "")

    def test_thumb_sem_foto(self):
        bem = self._mk_bem()
        result = self.admin.thumb(bem)
        self.assertEqual(result, "—")

    def test_foto_preview_sem_foto(self):
        bem = self._mk_bem()
        result = self.admin.foto_preview(bem)
        self.assertEqual(result, "—")


class TestBemPatrimonialAdminInlineInstances(AdminTestBase):
    def test_get_inline_instances_sem_obj(self):
        request = self.factory.get("/")
        request.user = self.gestor
        inlines = self.admin.get_inline_instances(request, None)
        self.assertEqual(inlines, [])

    def test_get_inline_instances_com_obj(self):
        bem = self._mk_bem()
        request = self.factory.get("/")
        request.user = self.gestor
        inlines = self.admin.get_inline_instances(request, bem)
        self.assertGreater(len(inlines), 0)


class TestBemPatrimonialAdminRenderChangeForm(AdminTestBase):
    def test_render_change_form_injeta_multi_block(self):
        request = self.factory.get("/admin/bem_patrimonial/bempatrimonial/add/")
        request.user = self.gestor
        request.POST = request.GET
        fake_html = '<div></div><!-- END form-container -->'
        mock_response = MagicMock()
        mock_response.rendered_content = fake_html
        mock_response.content = fake_html.encode("utf-8")
        mock_response.charset = "utf-8"
        with patch.object(type(self.admin).__mro__[1], "render_change_form", return_value=mock_response):
            context = {
                "opts": BemPatrimonial._meta,
                "inline_admin_formsets": [],
                "adminform": MagicMock(),
            }
            context["adminform"].form = MagicMock()
            context["adminform"].form.is_multipart = MagicMock(return_value=False)
            resp = self.admin.render_change_form(request, context)
        self.assertIn(b"multi-inline-root", resp.content or b"")


class TestBemPatrimonialAdminAddViewMulti(AdminTestBase):
    def test_add_view_multi_sem_linhas_retorna_erro(self):
        post = {
            "cadastro_modo": "multi",
            "unidade_administrativa": str(self.ua.pk),
            "nome": "Base",
            "descricao": "D",
            "valor_unitario": "10",
            "marca": "M",
            "modelo": "X",
            "numero_processo": "P",
            "multi_payload": "[]",
        }
        request = self.factory.post("/admin/bem_patrimonial/bempatrimonial/add/", post)
        request.user = self.gestor
        request.session = {}
        request._messages = FallbackStorage(request)
        with patch("bem_patrimonial.admins.bem_patrimonial.filtrar_ua_origem_por_escopo") as mock_filtrar:
            mock_filtrar.return_value = UnidadeAdministrativa.objects.filter(pk=self.ua.pk)
            resp = self.admin.add_view(request)
        self.assertEqual(BemPatrimonial.objects.count(), 0)
        self.assertNotIsInstance(resp, HttpResponseRedirect)

    def test_add_view_multi_com_uma_linha_valida_cria_bem(self):
        post = {
            "cadastro_modo": "multi",
            "unidade_administrativa": str(self.ua.pk),
            "nome": "Base",
            "descricao": "D",
            "valor_unitario": "10",
            "marca": "M",
            "modelo": "X",
            "numero_processo": "P",
            "multi_payload": json.dumps([
                {"localizacao": "Sala 1", "sem_numeracao": True},
            ]),
        }
        request = self.factory.post("/admin/bem_patrimonial/bempatrimonial/add/", post)
        request.user = self.gestor
        request.session = {}
        request._messages = FallbackStorage(request)
        with patch("bem_patrimonial.admins.bem_patrimonial.filtrar_ua_origem_por_escopo") as mock_filtrar:
            mock_filtrar.return_value = UnidadeAdministrativa.objects.filter(pk=self.ua.pk)
            resp = self.admin.add_view(request)
        self.assertIsInstance(resp, HttpResponseRedirect)
        self.assertEqual(BemPatrimonial.objects.count(), 1)
        bem = BemPatrimonial.objects.get()
        self.assertEqual(bem.localizacao, "Sala 1")
        self.assertTrue(bem.sem_numeracao)


class TestBemPatrimonialAdminSearchResults(AdminTestBase):
    def test_get_search_results_filtra_escopo(self):
        self._mk_bem(nome="Bem X")
        request = self.factory.get("/", {"q": "Bem"})
        request.user = self.gestor
        request.path = "/admin/bem_patrimonial/bempatrimonial/"
        qs = BemPatrimonial.objects.all()
        result_qs, use_distinct = self.admin.get_search_results(request, qs, "Bem")
        self.assertGreaterEqual(result_qs.count(), 1)

    def test_get_search_results_autocomplete_sem_ua_origem_retorna_none(self):
        request = self.factory.get("/autocomplete/", {
            "app_label": "bem_patrimonial",
            "model_name": "movimentacaobensitem",
            "field_name": "bem",
        })
        request.user = self.gestor
        request.path = "/admin/.../autocomplete/"
        qs = BemPatrimonial.objects.all()
        result_qs, _ = self.admin.get_search_results(request, qs, "")
        self.assertEqual(result_qs.count(), 0)


class TestBemPatrimonialAdminSaveStatus(AdminTestBase):
    def test_save_status_atribui_atualizado_por(self):
        bem = self._mk_bem()
        StatusBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            status=constants.APROVADO,
            atualizado_por=self.gestor,
        )
        form = MagicMock()
        formset = MagicMock()
        formset.model = StatusBemPatrimonial
        formset.save.return_value = []
        formset.deleted_objects = []
        formset.save_m2m = MagicMock()
        request = self.factory.post("/")
        request.user = self.operador
        self.admin.save_status(request, form, formset, True)
        formset.save_m2m.assert_called_once()
