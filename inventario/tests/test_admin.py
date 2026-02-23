from datetime import date
from unittest.mock import patch, MagicMock

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import TestCase, RequestFactory, Client
from django.urls import reverse
from django.utils import timezone

from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO

from inventario.admin import (
    AnoVigenciaSelectFilter,
    ParametroConciliacaoAnualAdminForm,
    ParametroConciliacaoAnualAdmin,
    ItemConciliacaoInline,
    ConciliacaoUAAdmin,
)
from inventario.models import (
    ConciliacaoUA,
    ItemConciliacao,
    OcorrenciaConciliacao,
    ParametroConciliacaoAnual,
)
from inventario import constants
from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants as bem_constants


class AdminTestBase(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.uo = criar_uo()
        self.ua = criar_ua(uo=self.uo)
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.usuario = Usuario.objects.create_user(
            username="admin_test",
            password="x",
            email="admin@test.com",
            is_staff=True,
            is_superuser=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.usuario.groups.add(grupo_gestor)


class TestAnoVigenciaSelectFilter(AdminTestBase):
    def test_lookups_sem_conciliacoes(self):
        filtro = AnoVigenciaSelectFilter(None, {}, ConciliacaoUA, ConciliacaoUAAdmin(ConciliacaoUA, self.site))
        lookups = filtro.lookups(self.factory.get("/"), ConciliacaoUAAdmin(ConciliacaoUA, self.site))
        self.assertEqual(lookups, [])

    def test_lookups_com_conciliacoes(self):
        ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        filtro = AnoVigenciaSelectFilter(None, {}, ConciliacaoUA, ConciliacaoUAAdmin(ConciliacaoUA, self.site))
        model_admin = ConciliacaoUAAdmin(ConciliacaoUA, self.site)
        request = self.factory.get("/")
        request.user = self.usuario
        lookups = filtro.lookups(request, model_admin)
        self.assertGreater(len(lookups), 0)
        self.assertEqual(lookups[0][0], lookups[0][1])

    def test_queryset_sem_value(self):
        filtro = AnoVigenciaSelectFilter(None, {}, ConciliacaoUA, ConciliacaoUAAdmin(ConciliacaoUA, self.site))
        qs = ConciliacaoUA.objects.all()
        request = self.factory.get("/")
        result = filtro.queryset(request, qs)
        self.assertEqual(result.count(), qs.count())

    def test_queryset_com_value(self):
        ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=date(2025, 6, 1),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        request = self.factory.get("/", {"ano_vigencia": "2025"})
        params = {"ano_vigencia": "2025"}
        filtro = AnoVigenciaSelectFilter(request, params, ConciliacaoUA, None)
        qs = ConciliacaoUA.objects.all()
        result = filtro.queryset(request, qs)
        self.assertEqual(result.count(), 1)


class TestParametroConciliacaoAnualAdminForm(AdminTestBase):
    def test_init_sem_request(self):
        form = ParametroConciliacaoAnualAdminForm()
        self.assertIsNone(getattr(form, "request", None))

    def test_init_com_user_com_uo(self):
        request = self.factory.get("/")
        request.user = self.usuario
        form = ParametroConciliacaoAnualAdminForm(request=request)
        self.assertEqual(form.fields["unidade_orcamentaria"].initial, self.uo.pk)
        self.assertTrue(form.fields["unidade_orcamentaria"].disabled)

    def test_init_instancia_com_pk_desabilita_uo(self):
        param = ParametroConciliacaoAnual.objects.create(
            ano_referencia=timezone.localdate().year - 1,
            periodo_inicial=date(2024, 1, 1),
            periodo_final=date(2024, 3, 31),
            ativo=True,
            unidade_orcamentaria=self.uo,
        )
        request = self.factory.get("/")
        request.user = self.usuario
        form = ParametroConciliacaoAnualAdminForm(instance=param, request=request)
        self.assertTrue(form.fields["unidade_orcamentaria"].disabled)

    def test_clean_com_superuser(self):
        request = self.factory.get("/")
        request.user = self.usuario
        form = ParametroConciliacaoAnualAdminForm(
            data={
                "unidade_orcamentaria": self.uo.pk,
                "ano_referencia": timezone.localdate().year - 1,
                "periodo_inicial": date(2024, 1, 1),
                "periodo_final": date(2024, 3, 31),
                "ativo": True,
            },
            request=request,
        )
        self.assertTrue(form.is_valid(), form.errors)


class TestParametroConciliacaoAnualAdmin(AdminTestBase):
    def setUp(self):
        super().setUp()
        self.admin = ParametroConciliacaoAnualAdmin(ParametroConciliacaoAnual, self.site)

    def test_get_queryset_com_ua(self):
        request = self.factory.get("/")
        request.user = self.usuario
        qs = self.admin.get_queryset(request)
        self.assertTrue(qs.query.where)

    def test_get_queryset_gestor_sem_ua(self):
        user_gestor = Usuario.objects.create_user(
            username="gestor_sem_ua",
            password="x",
            unidade_administrativa=None,
            unidade_orcamentaria=self.uo,
        )
        user_gestor.groups.add(Group.objects.get(name=GRUPO_GESTOR_PATRIMONIO))
        with patch.object(Usuario, "is_gestor_patrimonio", property(lambda s: True)):
            request = self.factory.get("/")
            request.user = user_gestor
            qs = self.admin.get_queryset(request)
            self.assertEqual(qs.count(), 0)

    def test_get_readonly_fields_com_obj(self):
        param = ParametroConciliacaoAnual.objects.create(
            ano_referencia=timezone.localdate().year - 1,
            periodo_inicial=date(2024, 1, 1),
            periodo_final=date(2024, 3, 31),
            ativo=True,
            unidade_orcamentaria=self.uo,
        )
        request = self.factory.get("/")
        request.user = self.usuario
        ro = self.admin.get_readonly_fields(request, param)
        self.assertIn("unidade_orcamentaria", ro)


class TestItemConciliacaoInline(AdminTestBase):
    def setUp(self):
        super().setUp()
        self.admin_conciliacao = ConciliacaoUAAdmin(ConciliacaoUA, self.site)
        self.inline = ItemConciliacaoInline(ItemConciliacao, self.site)

    def test_has_add_permission(self):
        request = self.factory.get("/")
        request.user = self.usuario
        self.assertFalse(self.inline.has_add_permission(request, None))

    def test_numero_patrimonial_bem(self):
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(conciliacao=conciliacao, bem=bem, atualizado_por=self.usuario)
        self.assertEqual(self.inline.numero_patrimonial_bem(item), "001.000000001-1")

    def test_numero_patrimonial_bem_sem_bem(self):
        item = MagicMock()
        item.bem = None
        self.assertEqual(self.inline.numero_patrimonial_bem(item), "-")

    def test_nome_bem(self):
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Mesa",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(conciliacao=conciliacao, bem=bem, atualizado_por=self.usuario)
        result = self.inline.nome_bem(item)
        self.assertIn("Mesa", result)

    def test_nome_bem_sem_nome(self):
        item = MagicMock()
        item.bem.nome = None
        self.assertEqual(self.inline.nome_bem(item), "-")

    def test_situacao_display_sem_obj(self):
        self.assertEqual(self.inline.situacao_display(None), "-")

    def test_situacao_display_com_obj(self):
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=constants.DIVERGENTE,
            atualizado_por=self.usuario,
        )
        result = self.inline.situacao_display(item)
        self.assertIn("Divergente", result)

    def test_observacao_resumida_sem_obj(self):
        self.assertEqual(self.inline.observacao_resumida(None), "-")

    def test_observacao_resumida_com_observacao(self):
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            observacao="Obs teste",
            atualizado_por=self.usuario,
        )
        result = self.inline.observacao_resumida(item)
        self.assertIn("Obs teste", result)

    def test_observacao_resumida_com_divergencia(self):
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=constants.DIVERGENTE,
            divergencia="Div",
            atualizado_por=self.usuario,
        )
        result = self.inline.observacao_resumida(item)
        self.assertIn("Divergência", result)

    def test_acoes_inline_sem_obj(self):
        self.assertEqual(self.inline.acoes_inline(None), "-")

    def test_acoes_inline_conciliacao_fechada(self):
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_FECHADO,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(conciliacao=conciliacao, bem=bem, atualizado_por=self.usuario)
        result = self.inline.acoes_inline(item)
        self.assertIn("fechada", result)

    def test_acoes_inline_permite_registrar(self):
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(conciliacao=conciliacao, bem=bem, atualizado_por=self.usuario)
        result = self.inline.acoes_inline(item)
        self.assertIn("Registrar", result)

    def test_acoes_inline_baixa_fisica_nao_permite(self):
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=constants.BAIXA_FISICA,
            atualizado_por=self.usuario,
        )
        result = self.inline.acoes_inline(item)
        self.assertIn("disabled", result)


class TestConciliacaoUAAdmin(AdminTestBase):
    def setUp(self):
        super().setUp()
        self.admin = ConciliacaoUAAdmin(ConciliacaoUA, self.site)

    def test_get_model_perms(self):
        request = self.factory.get("/")
        request.user = self.usuario
        perms = self.admin.get_model_perms(request)
        self.assertIn("view", perms)
        self.assertEqual(ConciliacaoUA._meta.verbose_name_plural, "Gerenciamento de Conciliações")

    def test_has_delete_permission(self):
        request = self.factory.get("/")
        request.user = self.usuario
        self.assertFalse(self.admin.has_delete_permission(request))

    def test_get_actions(self):
        request = self.factory.get("/")
        request.user = self.usuario
        self.assertEqual(self.admin.get_actions(request), {})

    def test_get_fieldsets_sem_obj(self):
        request = self.factory.get("/")
        request.user = self.usuario
        fieldsets = self.admin.get_fieldsets(request, None)
        self.assertEqual(len(fieldsets), 1)
        self.assertEqual(fieldsets[0][0], "Criar Conciliação")

    def test_get_fieldsets_com_obj(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        request = self.factory.get("/")
        request.user = self.usuario
        fieldsets = self.admin.get_fieldsets(request, conciliacao)
        self.assertGreater(len(fieldsets), 1)
        self.assertIn("Dados Básicos", [f[0] for f in fieldsets])

    def test_get_readonly_fields_conciliacao_fechada(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_FECHADO,
            criado_por=self.usuario,
        )
        request = self.factory.get("/")
        request.user = self.usuario
        ro = self.admin.get_readonly_fields(request, conciliacao)
        self.assertIn("unidade_administrativa", ro)
        self.assertIn("tipo", ro)
        self.assertIn("periodo_final", ro)

    def test_get_queryset(self):
        request = self.factory.get("/")
        request.user = self.usuario
        qs = self.admin.get_queryset(request)
        self.assertIsNotNone(qs)

    def test_status_display(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        result = self.admin.status_display(conciliacao)
        self.assertIn("Aberta", result)

    def test_periodo_display_sem_periodo(self):
        conciliacao = MagicMock()
        conciliacao.periodo_final = None
        self.assertEqual(self.admin.periodo_display(conciliacao), "-")

    def test_periodo_display_com_periodo(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=date(2025, 6, 15),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        result = self.admin.periodo_display(conciliacao)
        self.assertIn("15/06/2025", result)

    def test_total_itens_sem_pk(self):
        conciliacao = ConciliacaoUA()
        self.assertEqual(self.admin.total_itens(conciliacao), "-")

    def test_total_itens_com_itens(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        ItemConciliacao.objects.create(conciliacao=conciliacao, bem=bem, atualizado_por=self.usuario)
        result = self.admin.total_itens(conciliacao)
        self.assertIn("Total: 1", result)

    def test_acao_visualizar(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        result = self.admin.acao_visualizar(conciliacao)
        self.assertIn("Visualizar", result)
        self.assertIn(str(conciliacao.pk), result)


class TestConciliacaoUAAdminViews(AdminTestBase):
    def setUp(self):
        super().setUp()
        self.client = Client()
        self.client.force_login(self.usuario)

    def test_finalizar_conciliacao_view_get_redirect(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        url = reverse("admin:inventario_conciliacaoua_finalizar", args=[conciliacao.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    @patch("inventario.admin.finalizar_conciliacao")
    def test_finalizar_conciliacao_view_post(self, mock_finalizar):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )

        def _fechar(obj, user):
            obj.status = constants.CONCILIACAO_FECHADO
            obj.save(update_fields=["status"])

        mock_finalizar.side_effect = _fechar
        admin_instance = ConciliacaoUAAdmin(ConciliacaoUA, self.site)
        request = self.factory.post("/")
        request.user = self.usuario
        request.session = {}
        request._messages = FallbackStorage(request)
        with patch.object(admin_instance, "get_object", return_value=conciliacao):
            resp = admin_instance.finalizar_conciliacao_view(request, conciliacao.pk)
        self.assertEqual(resp.status_code, 302)
        conciliacao.refresh_from_db()
        self.assertEqual(conciliacao.status, constants.CONCILIACAO_FECHADO)
        mock_finalizar.assert_called_once_with(conciliacao, self.usuario)

    def test_finalizar_conciliacao_ja_fechada(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_FECHADO,
            criado_por=self.usuario,
        )
        url = reverse("admin:inventario_conciliacaoua_finalizar", args=[conciliacao.pk])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)

    def test_finalizar_conciliacao_nao_encontrada(self):
        url = reverse("admin:inventario_conciliacaoua_finalizar", args=[99999])
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 302)

    def test_registrar_ocorrencia_view_get(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(conciliacao=conciliacao, bem=bem, atualizado_por=self.usuario)
        admin_instance = ConciliacaoUAAdmin(ConciliacaoUA, self.site)
        request = _request_com_mensagens(self.factory, self.usuario, "get")
        resp = admin_instance.registrar_ocorrencia_view(request, item.pk)
        self.assertEqual(resp.status_code, 200)

    def test_registrar_ocorrencia_item_nao_encontrado(self):
        url = reverse("admin:inventario_item_registrar_ocorrencia", args=[99999])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_excluir_ocorrencia_view_get(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(conciliacao=conciliacao, bem=bem, atualizado_por=self.usuario)
        OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=constants.DIVERGENTE,
            divergencia="Div",
            registrado_por=self.usuario,
        )
        admin_instance = ConciliacaoUAAdmin(ConciliacaoUA, self.site)
        request = _request_com_mensagens(self.factory, self.usuario, "get")
        resp = admin_instance.excluir_ocorrencia_view(request, item.pk)
        self.assertEqual(resp.status_code, 200)

    def test_excluir_ocorrencia_item_nao_encontrado(self):
        url = reverse("admin:inventario_item_excluir_ocorrencia", args=[99999])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_changelist_view(self):
        admin_instance = ConciliacaoUAAdmin(ConciliacaoUA, self.site)
        request = _request_com_mensagens(self.factory, self.usuario, "get")
        with patch("inventario.admin.processar_conciliacao_anual_automatica"):
            resp = admin_instance.changelist_view(request)
        self.assertEqual(resp.status_code, 200)

    def test_changeform_view_show_save(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        admin_instance = ConciliacaoUAAdmin(ConciliacaoUA, self.site)
        request = _request_com_mensagens(self.factory, self.usuario, "get")
        resp = admin_instance.changeform_view(request, str(conciliacao.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context_data.get("show_save_and_add_another"))
        self.assertFalse(resp.context_data.get("show_save_and_continue"))


def _request_com_mensagens(factory, user, method="post"):
    request = getattr(factory, method)("/")
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


class TestConciliacaoUAAdminSaveModel(AdminTestBase):
    def setUp(self):
        super().setUp()
        self.admin = ConciliacaoUAAdmin(ConciliacaoUA, self.site)

    @patch("inventario.admin.criar_itens_conciliacao")
    def test_save_model_novo_obj_cria_itens(self, mock_criar):
        request = _request_com_mensagens(self.factory, self.usuario)
        conciliacao = ConciliacaoUA(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
        )
        form = MagicMock()
        form.changed_data = []
        self.admin.save_model(request, conciliacao, form, change=False)
        mock_criar.assert_called_once_with(conciliacao)

    def test_save_model_change_esta_aberto(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        request = _request_com_mensagens(self.factory, self.usuario)
        form = MagicMock()
        form.changed_data = []
        self.admin.save_model(request, conciliacao, form, change=True)
        conciliacao.refresh_from_db()
        self.assertEqual(conciliacao.status, constants.CONCILIACAO_EM_ABERTO)

    def test_save_model_change_status_em_changed_data(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        request = _request_com_mensagens(self.factory, self.usuario)
        form = MagicMock()
        form.changed_data = ["status"]
        self.admin.save_model(request, conciliacao, form, change=True)
        conciliacao.refresh_from_db()
        self.assertEqual(conciliacao.status, constants.CONCILIACAO_EM_ABERTO)

    def test_save_model_change_conciliacao_fechada(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_FECHADO,
            criado_por=self.usuario,
        )
        request = _request_com_mensagens(self.factory, self.usuario)
        form = MagicMock()
        form.changed_data = []
        self.admin.save_model(request, conciliacao, form, change=True)
        messages = list(request._messages)
        self.assertTrue(any("fechada" in str(m).lower() for m in messages))

    @patch("inventario.admin.registrar_ocorrencia")
    def test_registrar_ocorrencia_view_post(self, mock_registrar):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao, bem=bem, atualizado_por=self.usuario
        )
        admin_instance = ConciliacaoUAAdmin(ConciliacaoUA, self.site)
        request = _request_com_mensagens(self.factory, self.usuario, "post")
        request.POST = {
            "situacao": constants.ENCONTRADO,
            "observacao": "Teste",
            "divergencia": "",
        }
        resp = admin_instance.registrar_ocorrencia_view(request, item.pk)
        self.assertEqual(resp.status_code, 302)
        mock_registrar.assert_called_once()

    def test_registrar_ocorrencia_conciliacao_fechada(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_FECHADO,
            criado_por=self.usuario,
        )
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao, bem=bem, atualizado_por=self.usuario
        )
        admin_instance = ConciliacaoUAAdmin(ConciliacaoUA, self.site)
        request = _request_com_mensagens(self.factory, self.usuario, "get")
        resp = admin_instance.registrar_ocorrencia_view(request, item.pk)
        self.assertEqual(resp.status_code, 302)
        messages = list(request._messages)
        self.assertTrue(any("fechada" in str(m).lower() for m in messages))

    def test_registrar_ocorrencia_baixa_fisica_nao_permite(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=constants.BAIXA_FISICA,
            atualizado_por=self.usuario,
        )
        admin_instance = ConciliacaoUAAdmin(ConciliacaoUA, self.site)
        request = _request_com_mensagens(self.factory, self.usuario, "get")
        resp = admin_instance.registrar_ocorrencia_view(request, item.pk)
        self.assertEqual(resp.status_code, 302)
        messages = list(request._messages)
        self.assertTrue(any("baixa física" in str(m).lower() for m in messages))

    @patch("inventario.admin.excluir_ocorrencia")
    def test_excluir_ocorrencia_view_post(self, mock_excluir):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao, bem=bem, atualizado_por=self.usuario
        )
        OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=constants.DIVERGENTE,
            divergencia="Div",
            registrado_por=self.usuario,
        )
        admin_instance = ConciliacaoUAAdmin(ConciliacaoUA, self.site)
        request = _request_com_mensagens(self.factory, self.usuario, "post")
        resp = admin_instance.excluir_ocorrencia_view(request, item.pk)
        self.assertEqual(resp.status_code, 302)
        mock_excluir.assert_called_once()

    def test_excluir_ocorrencia_conciliacao_fechada(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_FECHADO,
            criado_por=self.usuario,
        )
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao, bem=bem, atualizado_por=self.usuario
        )
        admin_instance = ConciliacaoUAAdmin(ConciliacaoUA, self.site)
        request = _request_com_mensagens(self.factory, self.usuario, "get")
        resp = admin_instance.excluir_ocorrencia_view(request, item.pk)
        self.assertEqual(resp.status_code, 302)
        messages = list(request._messages)
        self.assertTrue(any("fechada" in str(m).lower() for m in messages))

    def test_total_itens_com_detalhes_por_situacao(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        bem1 = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-1",
            nome="Bem 1",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        bem2 = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000002-2",
            nome="Bem 2",
            valor_unitario=200,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem1,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
            atualizado_por=self.usuario,
        )
        ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem2,
            situacao=constants.NAO_ENCONTRADO,
            atualizado_por=self.usuario,
        )
        result = self.admin.total_itens(conciliacao)
        self.assertIn("Total: 2", result)
        self.assertIn("Encontrados: 1", result)
        self.assertIn("Não encontrados: 1", result)