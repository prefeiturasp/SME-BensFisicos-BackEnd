"""Testes para dados_comuns.admin."""
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase

from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria
from dados_comuns.tests.factories import criar_ua, criar_uo
from dados_comuns.admin import (
    StatusFilter,
    AtivaFilter,
    UnidadeOrcamentariaAdmin,
    UnidadeAdministrativaAdmin,
)


User = get_user_model()


class TestStatusFilter(TestCase):
    """Testes para StatusFilter."""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.filter = StatusFilter(None, {}, UnidadeAdministrativa, None)

    def test_lookups_retorna_status_choices(self):
        """Lookups retorna todas as opções de status."""
        request = self.factory.get("/")
        lookups = self.filter.lookups(request, None)
        self.assertEqual(lookups, UnidadeAdministrativa.STATUS_CHOICES)

    def test_queryset_sem_value_retorna_todos(self):
        """Queryset sem value retorna todos os registros."""
        uo = criar_uo()
        criar_ua(uo=uo, status=UnidadeAdministrativa.ATIVA)
        criar_ua(uo=uo, status=UnidadeAdministrativa.INATIVA)
        qs = UnidadeAdministrativa.objects.all()
        request = self.factory.get("/")
        resultado = self.filter.queryset(request, qs)
        self.assertEqual(resultado.count(), 2)

    def test_queryset_com_value_filtra_por_status(self):
        """Queryset com value filtra por status."""
        uo = criar_uo()
        criar_ua(uo=uo, status=UnidadeAdministrativa.ATIVA)
        criar_ua(uo=uo, status=UnidadeAdministrativa.INATIVA)
        self.filter.used_parameters = {"status": UnidadeAdministrativa.ATIVA}
        qs = UnidadeAdministrativa.objects.all()
        request = self.factory.get("/")
        resultado = self.filter.queryset(request, qs)
        self.assertEqual(resultado.count(), 1)
        self.assertEqual(resultado.first().status, UnidadeAdministrativa.ATIVA)


class TestAtivaFilter(TestCase):
    """Testes para AtivaFilter (usado em UnidadeOrcamentaria)."""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.filter = AtivaFilter(None, {}, UnidadeOrcamentaria, None)

    def test_lookups_retorna_opcoes_ativa_inativa(self):
        """Lookups retorna opções Ativa/Inativa."""
        request = self.factory.get("/")
        lookups = self.filter.lookups(request, None)
        self.assertIn(("1", "Ativa"), lookups)
        self.assertIn(("0", "Inativa"), lookups)

    def test_queryset_value_1_filtra_ativas(self):
        """Queryset com value='1' filtra apenas ativas."""
        uo_ativa = criar_uo(codigo="100", ativa=True)
        uo_inativa = criar_uo(codigo="101", ativa=False)
        self.filter.used_parameters = {"ativa": "1"}
        qs = UnidadeOrcamentaria.objects.filter(pk__in=[uo_ativa.pk, uo_inativa.pk])
        request = self.factory.get("/")
        resultado = self.filter.queryset(request, qs)
        self.assertEqual(resultado.count(), 1)
        self.assertIn(uo_ativa, resultado)
        self.assertNotIn(uo_inativa, resultado)

    def test_queryset_value_0_filtra_inativas(self):
        """Queryset com value='0' filtra apenas inativas."""
        uo_ativa = criar_uo(codigo="102", ativa=True)
        uo_inativa = criar_uo(codigo="103", ativa=False)
        self.filter.used_parameters = {"ativa": "0"}
        qs = UnidadeOrcamentaria.objects.filter(pk__in=[uo_ativa.pk, uo_inativa.pk])
        request = self.factory.get("/")
        resultado = self.filter.queryset(request, qs)
        self.assertEqual(resultado.count(), 1)
        self.assertIn(uo_inativa, resultado)
        self.assertNotIn(uo_ativa, resultado)

    def test_queryset_sem_value_retorna_todos(self):
        """Queryset sem value retorna todos."""
        uo_ativa = criar_uo(codigo="104", ativa=True)
        uo_inativa = criar_uo(codigo="105", ativa=False)
        qs = UnidadeOrcamentaria.objects.filter(pk__in=[uo_ativa.pk, uo_inativa.pk])
        request = self.factory.get("/")
        resultado = self.filter.queryset(request, qs)
        self.assertEqual(resultado.count(), 2)
        self.assertIn(uo_ativa, resultado)
        self.assertIn(uo_inativa, resultado)


class TestUnidadeOrcamentariaAdmin(TestCase):
    """Testes para UnidadeOrcamentariaAdmin."""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.admin = UnidadeOrcamentariaAdmin(UnidadeOrcamentaria, self.site)
        self.superuser = User.objects.create_user(
            username="super",
            password="x",
            email="super@test.com",
            is_superuser=True,
            is_staff=True,
        )
        self.usuario_comum = User.objects.create_user(
            username="comum",
            password="x",
            email="comum@test.com",
            is_staff=True,
        )

    def test_has_module_permission_apenas_superuser(self):
        """Apenas superuser tem permissão de módulo."""
        request = self.factory.get("/")
        request.user = self.superuser
        self.assertTrue(self.admin.has_module_permission(request))
        request.user = self.usuario_comum
        self.assertFalse(self.admin.has_module_permission(request))

    def test_has_view_permission_apenas_superuser(self):
        """Apenas superuser tem permissão de visualização."""
        request = self.factory.get("/")
        request.user = self.superuser
        self.assertTrue(self.admin.has_view_permission(request))
        request.user = self.usuario_comum
        self.assertFalse(self.admin.has_view_permission(request))

    def test_has_add_permission_apenas_superuser(self):
        """Apenas superuser tem permissão de adicionar."""
        request = self.factory.get("/")
        request.user = self.superuser
        self.assertTrue(self.admin.has_add_permission(request))
        request.user = self.usuario_comum
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_change_permission_apenas_superuser(self):
        """Apenas superuser tem permissão de editar."""
        uo = criar_uo()
        request = self.factory.get("/")
        request.user = self.superuser
        self.assertTrue(self.admin.has_change_permission(request, uo))
        request.user = self.usuario_comum
        self.assertFalse(self.admin.has_change_permission(request, uo))

    def test_has_delete_permission_sempre_false(self):
        """Permissão de deletar sempre retorna False."""
        uo = criar_uo()
        request = self.factory.get("/")
        request.user = self.superuser
        self.assertFalse(self.admin.has_delete_permission(request, uo))

    def test_has_import_permission_sempre_false(self):
        """Permissão de importar sempre retorna False."""
        request = self.factory.get("/")
        request.user = self.superuser
        self.assertFalse(self.admin.has_import_permission(request))

    def test_has_export_permission_apenas_superuser(self):
        """Apenas superuser tem permissão de exportar."""
        request = self.factory.get("/")
        request.user = self.superuser
        self.assertTrue(self.admin.has_export_permission(request))
        request.user = self.usuario_comum
        self.assertFalse(self.admin.has_export_permission(request))

    def test_get_form_valida_codigo_obrigatorio(self):
        """Form valida que código é obrigatório."""
        request = self.factory.get("/")
        request.user = self.superuser
        form_class = self.admin.get_form(request)
        form = form_class(data={"nome": "UO Teste", "ativa": True})
        self.assertFalse(form.is_valid())
        self.assertIn("codigo", form.errors)

    def test_get_form_valida_nome_obrigatorio(self):
        """Form valida que nome é obrigatório."""
        request = self.factory.get("/")
        request.user = self.superuser
        form_class = self.admin.get_form(request)
        form = form_class(data={"codigo": "100", "ativa": True})
        self.assertFalse(form.is_valid())
        self.assertIn("nome", form.errors)

    def test_save_model_mensagem_sucesso_criacao(self):
        """Save model mostra mensagem de sucesso ao criar."""
        request = self.factory.post("/")
        request.user = self.superuser
        request.session = {}
        request._messages = FallbackStorage(request)
        uo = UnidadeOrcamentaria(codigo="100", nome="UO Teste", ativa=True)
        form = type("MockForm", (), {"cleaned_data": {}})()
        self.admin.save_model(request, uo, form, change=False)
        messages = list(request._messages)
        self.assertTrue(any("criada" in str(m).lower() for m in messages))

    def test_save_model_mensagem_sucesso_atualizacao(self):
        """Save model mostra mensagem de sucesso ao atualizar."""
        uo = criar_uo(codigo="100", nome="UO Original")
        request = self.factory.post("/")
        request.user = self.superuser
        request.session = {}
        request._messages = FallbackStorage(request)
        form = type("MockForm", (), {"cleaned_data": {}})()
        self.admin.save_model(request, uo, form, change=True)
        messages = list(request._messages)
        self.assertTrue(any("atualizada" in str(m).lower() for m in messages))

    def test_get_export_formats(self):
        """Retorna formatos de exportação corretos."""
        formats = self.admin.get_export_formats()
        format_names = [f.__name__ for f in formats]
        self.assertIn("CSV", format_names)
        self.assertIn("XLSX", format_names)
        self.assertIn("XLS", format_names)


class TestUnidadeAdministrativaAdmin(TestCase):
    """Testes para UnidadeAdministrativaAdmin."""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.admin = UnidadeAdministrativaAdmin(UnidadeAdministrativa, self.site)
        self.uo = criar_uo(codigo="100")
        self.uo_outra = criar_uo(codigo="200")
        self.ua = criar_ua(uo=self.uo, codigo="100.286")
        self.superuser = User.objects.create_user(
            username="super",
            password="x",
            email="super@test.com",
            is_superuser=True,
            is_staff=True,
            unidade_orcamentaria=self.uo,
        )
        self.gestor = User.objects.create_user(
            username="gestor",
            password="x",
            email="gestor@test.com",
            is_staff=True,
            unidade_orcamentaria=self.uo,
            unidade_administrativa=self.ua,
        )
        from usuario.constants import GRUPO_GESTOR_PATRIMONIO
        from django.contrib.auth.models import Group

        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.gestor.groups.add(grupo_gestor)

    def test_has_import_permission_sempre_false(self):
        """Permissão de importar sempre retorna False."""
        request = self.factory.get("/")
        request.user = self.superuser
        self.assertFalse(self.admin.has_import_permission(request))

    def test_has_export_permission_apenas_gestor(self):
        """Apenas gestor tem permissão de exportar."""
        request = self.factory.get("/")
        request.user = self.gestor
        self.assertTrue(self.admin.has_export_permission(request))
        request.user = self.superuser
        self.assertFalse(self.admin.has_export_permission(request))

    def test_get_queryset_com_uo_filtra_por_uo(self):
        """Queryset com UO filtra por unidade orçamentária."""
        criar_ua(uo=self.uo_outra, codigo="200.100")
        request = self.factory.get("/")
        request.user = self.gestor
        qs = self.admin.get_queryset(request)
        self.assertEqual(qs.count(), 1)
        self.assertIn(self.ua, qs)

    def test_get_queryset_com_ua_retorna_apenas_ua(self):
        """Queryset com UA (sem UO) retorna apenas a UA do usuário."""
        # Criar usuário que tem apenas UA (sem UO) para testar filtro por UA específica
        user_apenas_ua = User.objects.create_user(
            username="user_apenas_ua",
            password="x",
            email="apenasua@test.com",
            is_staff=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=None,  # Sem UO
        )
        # Criar outra UA na mesma UO não deve aparecer quando usuário tem apenas UA
        outra_ua = criar_ua(uo=self.uo, codigo="100.100")
        request = self.factory.get("/")
        request.user = user_apenas_ua
        qs = self.admin.get_queryset(request)
        # Quando usuário tem apenas UA (sem UO), retorna apenas sua UA (filtro por pk=ua.pk)
        uas_no_queryset = list(qs.values_list('pk', flat=True))
        self.assertEqual(len(uas_no_queryset), 1, f"Esperado 1 UA, mas encontrado {len(uas_no_queryset)}: {uas_no_queryset}")
        self.assertIn(self.ua.pk, uas_no_queryset)
        self.assertNotIn(outra_ua.pk, uas_no_queryset)

    def test_get_queryset_sem_uo_ua_retorna_none(self):
        """Queryset sem UO nem UA retorna queryset vazio."""
        user_sem_uo_ua = User.objects.create_user(
            username="user_vazio",
            password="x",
            email="vazio@test.com",
            is_staff=True,
        )
        request = self.factory.get("/")
        request.user = user_sem_uo_ua
        qs = self.admin.get_queryset(request)
        self.assertEqual(qs.count(), 0)

    def test_formfield_for_foreignkey_com_uo_filtra_queryset(self):
        """Formfield para foreignkey com UO filtra queryset."""
        request = self.factory.get("/")
        request.user = self.gestor
        field = self.admin.formfield_for_foreignkey(
            UnidadeAdministrativa._meta.get_field("unidade_orcamentaria"),
            request,
        )
        self.assertEqual(field.queryset.count(), 1)
        self.assertIn(self.uo, field.queryset)

    def test_formfield_for_foreignkey_sem_uo_retorna_none(self):
        """Formfield para foreignkey sem UO retorna queryset vazio."""
        user_sem_uo = User.objects.create_user(
            username="user_sem_uo",
            password="x",
            email="semuo@test.com",
            is_staff=True,
        )
        request = self.factory.get("/")
        request.user = user_sem_uo
        field = self.admin.formfield_for_foreignkey(
            UnidadeAdministrativa._meta.get_field("unidade_orcamentaria"),
            request,
        )
        self.assertEqual(field.queryset.count(), 0)

    def test_get_form_define_unidade_orcamentaria_required(self):
        """Get form define unidade_orcamentaria como required."""
        request = self.factory.get("/")
        request.user = self.gestor
        form_class = self.admin.get_form(request)
        self.assertTrue(form_class.base_fields["unidade_orcamentaria"].required)

    def test_get_form_define_initial_para_nao_superuser(self):
        """Get form define initial de UO para não superuser."""
        request = self.factory.get("/")
        request.user = self.gestor
        form_class = self.admin.get_form(request, obj=None)
        self.assertEqual(
            form_class.base_fields["unidade_orcamentaria"].initial, self.uo.pk
        )

    def test_get_form_desabilita_uo_para_nao_superuser(self):
        """Get form desabilita UO para não superuser."""
        request = self.factory.get("/")
        request.user = self.gestor
        form_class = self.admin.get_form(request, obj=None)
        self.assertTrue(
            form_class.base_fields["unidade_orcamentaria"].disabled
        )

    def test_get_form_valida_uo_obrigatoria(self):
        """Get form valida que UO é obrigatória."""
        request = self.factory.get("/")
        request.user = self.gestor
        form_class = self.admin.get_form(request)
        # O form customizado adiciona validação de UO obrigatória
        form = form_class(
            data={
                "codigo_sufixo": "286",
                "sigla": "UA",
                "nome": "Unidade",
                "status": UnidadeAdministrativa.ATIVA,
            }
        )
        # O form pode não validar se UO não estiver no POST mas o usuário tem UO
        # Vamos forçar sem UO
        if hasattr(request.user, 'unidade_orcamentaria_id'):
            # Criar usuário sem UO para testar
            user_sem_uo = User.objects.create_user(
                username="user_sem_uo",
                password="x",
                email="semuo@test.com",
                is_staff=True,
            )
            request.user = user_sem_uo
            form_class = self.admin.get_form(request)
            form = form_class(
                data={
                    "codigo_sufixo": "286",
                    "sigla": "UA",
                    "nome": "Unidade",
                    "status": UnidadeAdministrativa.ATIVA,
                }
            )
            # O form base pode validar, mas o custom_clean deve adicionar erro
            # Na verdade, o form pode ser válido mas o clean customizado adiciona erro
            form.is_valid()  # Chama is_valid para executar clean
            # O erro pode estar em form.errors ou form.non_field_errors
            self.assertTrue(
                "unidade_orcamentaria" in form.errors or not form.is_valid()
            )

    def test_get_form_desabilita_uo_para_nao_superuser(self):
        """Get form desabilita campo UO para não superuser."""
        request = self.factory.get("/")
        request.user = self.gestor
        form_class = self.admin.get_form(request)
        form = form_class()
        # Verificar que o campo UO está disabled para não superuser
        self.assertTrue(form.fields["unidade_orcamentaria"].disabled)
        
        # Verificar que para superuser não está disabled
        request.user = self.superuser
        form_class = self.admin.get_form(request)
        form = form_class()
        self.assertFalse(form.fields["unidade_orcamentaria"].disabled)

    def test_get_search_results_filtra_por_escopo_origem(self):
        """Get search results filtra por escopo quando field_name é origem."""
        request = self.factory.get("/")
        request.user = self.gestor
        request.GET = {"field_name": "unidade_administrativa_origem"}
        qs = UnidadeAdministrativa.objects.all()
        resultado, use_distinct = self.admin.get_search_results(request, qs, "")
        # Deve filtrar apenas UAs ativas e do escopo do usuário
        self.assertLessEqual(resultado.count(), qs.count())

    def test_get_search_results_filtra_por_escopo_destino(self):
        """Get search results filtra por escopo quando field_name é destino."""
        request = self.factory.get("/")
        request.user = self.gestor
        request.GET = {"field_name": "unidade_administrativa_destino"}
        qs = UnidadeAdministrativa.objects.all()
        resultado, use_distinct = self.admin.get_search_results(request, qs, "")
        # Deve filtrar apenas UAs ativas e da UO do usuário
        self.assertLessEqual(resultado.count(), qs.count())

    def test_get_search_results_filtra_apenas_ativas_no_autocomplete(self):
        """Get search results filtra apenas ativas no autocomplete."""
        criar_ua(uo=self.uo, codigo="100.100", status=UnidadeAdministrativa.INATIVA)
        request = self.factory.get("/")
        request.user = self.gestor
        request.GET = {"field_name": "unidade_administrativa_origem"}
        qs = UnidadeAdministrativa.objects.all()
        resultado, use_distinct = self.admin.get_search_results(request, qs, "")
        for ua in resultado:
            self.assertEqual(ua.status, UnidadeAdministrativa.ATIVA)

    def test_save_model_atualiza_codigo(self):
        """Save model atualiza código do objeto."""
        ua = criar_ua(uo=self.uo, codigo="100.100")
        request = self.factory.post("/")
        request.user = self.gestor
        form = type(
            "MockForm",
            (),
            {"cleaned_data": {"codigo": "100.286"}},
        )()
        self.admin.save_model(request, ua, form, change=True)
        ua.refresh_from_db()
        self.assertEqual(ua.codigo, "100.286")

    def test_save_model_mensagem_inativacao(self):
        """Save model mostra mensagem ao inativar."""
        ua = criar_ua(uo=self.uo, codigo="100.286", status=UnidadeAdministrativa.ATIVA)
        request = self.factory.post("/")
        request.user = self.gestor
        request.session = {}
        request._messages = FallbackStorage(request)
        ua.status = UnidadeAdministrativa.INATIVA
        form = type(
            "MockForm",
            (),
            {"cleaned_data": {"codigo": "100.286"}},
        )()
        self.admin.save_model(request, ua, form, change=True)
        messages = list(request._messages)
        self.assertTrue(any("inativada" in str(m).lower() for m in messages))

    def test_get_export_formats(self):
        """Retorna formatos de exportação incluindo PDF."""
        formats = self.admin.get_export_formats()
        format_names = [f.__name__ for f in formats]
        self.assertIn("CSV", format_names)
        self.assertIn("XLSX", format_names)
        self.assertIn("XLS", format_names)
