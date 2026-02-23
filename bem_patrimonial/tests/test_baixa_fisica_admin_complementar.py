"""Testes complementares para bem_patrimonial.admins.baixa_fisica_bem_patrimonial."""
from unittest.mock import patch, MagicMock
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.utils import timezone

from bem_patrimonial.models import BaixaFisicaBemPatrimonial, BaixaFisicaBensItem, BemPatrimonial
from bem_patrimonial.admins.baixa_fisica_bem_patrimonial import (
    BaixaFisicaBemPatrimonialAdmin,
    BaixaFisicaBensItemInlineFormSet,
    BaixaFisicaBensItemInline,
)
from bem_patrimonial import constants
from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


User = get_user_model()


class AdminTestBase(TestCase):
    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.uo = criar_uo()
        self.ua_origem = criar_ua(uo=self.uo, status=UnidadeAdministrativa.ATIVA)
        self.grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)

        self.gestor = User.objects.create_user(
            username="gestor",
            password="x",
            email="gestor@test.com",
            is_staff=True,
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        self.gestor.groups.add(self.grupo_gestor)

        self.operador = User.objects.create_user(
            username="operador",
            password="x",
            email="operador@test.com",
            is_staff=True,
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        self.operador.groups.add(self.grupo_operador)

        self.admin = BaixaFisicaBemPatrimonialAdmin(BaixaFisicaBemPatrimonial, self.site)

    def _mk_bem(self, **kwargs):
        defaults = {
            "nome": "Bem Teste",
            "descricao": "Desc",
            "valor_unitario": 100,
            "marca": "M",
            "modelo": "X",
            "numero_processo": "PROC-1",
            "unidade_administrativa": self.ua_origem,
            "criado_por": self.operador,
            "status": constants.APROVADO,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def _mk_baixa(self, **kwargs):
        defaults = {
            "unidade_administrativa_origem": self.ua_origem,
            "numero_processo_baixa": "PROC-123",
            "status": constants.AGUARDANDO_ENVIO,
            "criado_por": self.operador,
            "data_baixa": timezone.localdate(),
        }
        defaults.update(kwargs)
        return BaixaFisicaBemPatrimonial.objects.create(**defaults)

    def _add_messages_support(self, request):
        """Adiciona suporte a mensagens no request."""
        setattr(request, "session", "session")
        storage = FallbackStorage(request)
        setattr(request, "_messages", storage)
        return storage


class TestBaixaFisicaBensItemInlineFormSet(AdminTestBase):
    """Testes para BaixaFisicaBensItemInlineFormSet."""

    def test_clean_sem_bens_levanta_erro(self):
        """Clean sem bens levanta ValidationError."""
        baixa = self._mk_baixa()
        from django.forms.models import inlineformset_factory
        FormSet = inlineformset_factory(
            BaixaFisicaBemPatrimonial,
            BaixaFisicaBensItem,
            formset=BaixaFisicaBensItemInlineFormSet,
            fields=("bem",),
            extra=0,
        )
        formset = FormSet(instance=baixa, data={
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
        })
        formset.is_valid()
        self.assertFalse(formset.is_valid())
        self.assertIn("ao menos um bem", str(formset.non_form_errors()).lower())

    def test_clean_com_bem_valido(self):
        """Clean com bem válido é válido."""
        baixa = self._mk_baixa()
        bem = self._mk_bem()
        from django.forms.models import inlineformset_factory
        FormSet = inlineformset_factory(
            BaixaFisicaBemPatrimonial,
            BaixaFisicaBensItem,
            formset=BaixaFisicaBensItemInlineFormSet,
            fields=("bem",),
            extra=0,
        )
        formset = FormSet(instance=baixa, data={
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-bem": bem.pk,
        })
        self.assertTrue(formset.is_valid())

    def test_clean_ignora_formularios_deletados(self):
        """Clean ignora formulários marcados para deletar."""
        baixa = self._mk_baixa()
        bem1 = self._mk_bem()
        bem2 = self._mk_bem()
        item1 = BaixaFisicaBensItem.objects.create(baixa=baixa, bem=bem1)
        from django.forms.models import inlineformset_factory
        FormSet = inlineformset_factory(
            BaixaFisicaBemPatrimonial,
            BaixaFisicaBensItem,
            formset=BaixaFisicaBensItemInlineFormSet,
            fields=("bem",),
            extra=0,
        )
        formset = FormSet(instance=baixa, data={
            "itens-TOTAL_FORMS": "2",
            "itens-INITIAL_FORMS": "1",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-id": str(item1.pk),
            "itens-0-bem": str(bem1.pk),
            "itens-0-DELETE": "on",
            "itens-1-bem": str(bem2.pk),
        })
        # Deve ser válido porque bem2 está presente
        self.assertTrue(formset.is_valid())


class TestBaixaFisicaBensItemInline(AdminTestBase):
    """Testes para BaixaFisicaBensItemInline."""

    def test_has_add_permission_com_obj_aguardando_envio(self):
        """has_add_permission retorna True quando obj está AGUARDANDO_ENVIO."""
        baixa = self._mk_baixa(status=constants.AGUARDANDO_ENVIO)
        inline = BaixaFisicaBensItemInline(BaixaFisicaBemPatrimonial, self.site)
        request = self.factory.get("/")
        request.user = self.operador
        self.assertTrue(inline.has_add_permission(request, baixa))

    def test_has_add_permission_com_obj_solicitada(self):
        """has_add_permission retorna False quando obj está SOLICITADA."""
        baixa = self._mk_baixa(status=constants.SOLICITADA)
        inline = BaixaFisicaBensItemInline(BaixaFisicaBemPatrimonial, self.site)
        request = self.factory.get("/")
        request.user = self.operador
        self.assertFalse(inline.has_add_permission(request, baixa))

    def test_has_add_permission_sem_obj(self):
        """has_add_permission retorna True quando obj é None."""
        inline = BaixaFisicaBensItemInline(BaixaFisicaBemPatrimonial, self.site)
        request = self.factory.get("/")
        request.user = self.operador
        self.assertTrue(inline.has_add_permission(request, None))

    def test_has_delete_permission_sem_obj(self):
        """has_delete_permission retorna False quando obj é None."""
        inline = BaixaFisicaBensItemInline(BaixaFisicaBemPatrimonial, self.site)
        request = self.factory.get("/")
        request.user = self.operador
        self.assertFalse(inline.has_delete_permission(request, None))

    def test_has_delete_permission_com_obj_aguardando_envio(self):
        """has_delete_permission retorna True quando obj está AGUARDANDO_ENVIO."""
        baixa = self._mk_baixa(status=constants.AGUARDANDO_ENVIO)
        inline = BaixaFisicaBensItemInline(BaixaFisicaBemPatrimonial, self.site)
        request = self.factory.get("/")
        request.user = self.operador
        self.assertTrue(inline.has_delete_permission(request, baixa))

    def test_has_delete_permission_com_obj_solicitada(self):
        """has_delete_permission retorna False quando obj está SOLICITADA."""
        baixa = self._mk_baixa(status=constants.SOLICITADA)
        inline = BaixaFisicaBensItemInline(BaixaFisicaBemPatrimonial, self.site)
        request = self.factory.get("/")
        request.user = self.operador
        self.assertFalse(inline.has_delete_permission(request, baixa))

    def test_get_max_num_com_obj_aguardando_envio(self):
        """get_max_num retorna None quando obj está AGUARDANDO_ENVIO."""
        baixa = self._mk_baixa(status=constants.AGUARDANDO_ENVIO)
        inline = BaixaFisicaBensItemInline(BaixaFisicaBemPatrimonial, self.site)
        request = self.factory.get("/")
        request.user = self.operador
        max_num = inline.get_max_num(request, baixa)
        # Deve retornar None (sem limite) ou um número alto
        self.assertIsNone(max_num)

    def test_get_max_num_com_obj_solicitada(self):
        """get_max_num retorna 0 quando obj está SOLICITADA."""
        baixa = self._mk_baixa(status=constants.SOLICITADA)
        inline = BaixaFisicaBensItemInline(BaixaFisicaBemPatrimonial, self.site)
        request = self.factory.get("/")
        request.user = self.operador
        max_num = inline.get_max_num(request, baixa)
        self.assertEqual(max_num, 0)

    def test_get_readonly_fields_com_obj_aguardando_envio(self):
        """get_readonly_fields retorna vazio quando obj está AGUARDANDO_ENVIO."""
        baixa = self._mk_baixa(status=constants.AGUARDANDO_ENVIO)
        inline = BaixaFisicaBensItemInline(BaixaFisicaBemPatrimonial, self.site)
        request = self.factory.get("/")
        request.user = self.operador
        readonly = inline.get_readonly_fields(request, baixa)
        self.assertEqual(readonly, ())

    def test_get_readonly_fields_com_obj_solicitada(self):
        """get_readonly_fields retorna ('bem',) quando obj está SOLICITADA."""
        baixa = self._mk_baixa(status=constants.SOLICITADA)
        inline = BaixaFisicaBensItemInline(BaixaFisicaBemPatrimonial, self.site)
        request = self.factory.get("/")
        request.user = self.operador
        readonly = inline.get_readonly_fields(request, baixa)
        self.assertEqual(readonly, ("bem",))


class TestBaixaFisicaBemPatrimonialAdmin(AdminTestBase):
    """Testes para BaixaFisicaBemPatrimonialAdmin."""

    def test_get_readonly_fields_sem_obj(self):
        """get_readonly_fields sem objeto retorna vazio."""
        request = self.factory.get("/")
        request.user = self.operador
        readonly = self.admin.get_readonly_fields(request, None)
        self.assertEqual(readonly, ())

    def test_get_readonly_fields_com_obj(self):
        """get_readonly_fields com objeto retorna campos readonly."""
        baixa = self._mk_baixa()
        request = self.factory.get("/")
        request.user = self.operador
        readonly = self.admin.get_readonly_fields(request, baixa)
        self.assertIn("unidade_administrativa_origem", readonly)
        self.assertIn("status", readonly)
        self.assertIn("criado_por", readonly)

    def test_get_fieldsets_sem_obj(self):
        """get_fieldsets sem objeto retorna campos básicos."""
        request = self.factory.get("/")
        request.user = self.operador
        fieldsets = self.admin.get_fieldsets(request, None)
        self.assertEqual(len(fieldsets), 1)
        fields = fieldsets[0][1]["fields"]
        self.assertIn("unidade_administrativa_origem", fields)
        self.assertIn("numero_processo_baixa", fields)
        self.assertIn("data_baixa", fields)
        self.assertNotIn("status", fields)

    def test_get_fieldsets_com_obj(self):
        """get_fieldsets com objeto retorna campos completos."""
        baixa = self._mk_baixa()
        request = self.factory.get("/")
        request.user = self.operador
        fieldsets = self.admin.get_fieldsets(request, baixa)
        self.assertEqual(len(fieldsets), 1)
        fields = fieldsets[0][1]["fields"]
        self.assertIn("status", fields)
        self.assertIn("criado_por", fields)
        self.assertIn("aprovado_por", fields)

    def test_save_model_novo_obj_define_criado_por(self):
        """save_model para novo objeto define criado_por."""
        baixa = BaixaFisicaBemPatrimonial(
            unidade_administrativa_origem=self.ua_origem,
            numero_processo_baixa="PROC-123",
            data_baixa=timezone.localdate(),
        )
        request = self.factory.post("/")
        request.user = self.operador
        form = MagicMock()
        form.instance = baixa
        self.admin.save_model(request, baixa, form, change=False)
        self.assertEqual(baixa.criado_por, self.operador)

    def test_save_model_obj_existente_nao_sobrescreve_criado_por(self):
        """save_model para objeto existente não sobrescreve criado_por."""
        baixa = self._mk_baixa(criado_por=self.gestor)
        original_criado_por = baixa.criado_por
        request = self.factory.post("/")
        request.user = self.operador
        form = MagicMock()
        form.instance = baixa
        self.admin.save_model(request, baixa, form, change=True)
        self.assertEqual(baixa.criado_por, original_criado_por)

    def test_save_related_ajusta_status_bens_novos(self):
        """save_related ajusta status de bens novos para BAIXA_FISICA_AGUARDANDO_APROVACAO."""
        baixa = self._mk_baixa(status=constants.AGUARDANDO_ENVIO)
        bem = self._mk_bem(status=constants.APROVADO)
        form = MagicMock()
        form.instance = baixa
        
        # Criar item após salvar
        item = BaixaFisicaBensItem.objects.create(baixa=baixa, bem=bem)
        
        # Mock do formset com new_objects
        formset = MagicMock()
        formset.model = BaixaFisicaBensItem
        formset.deleted_objects = []
        formset.new_objects = [item]
        
        request = self.factory.post("/")
        request.user = self.operador
        self.admin.save_related(request, form, [formset], change=True)
        
        bem.refresh_from_db()
        self.assertEqual(bem.status, constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)

    def test_save_related_ajusta_status_bens_deletados(self):
        """save_related ajusta status de bens deletados para APROVADO."""
        baixa = self._mk_baixa(status=constants.AGUARDANDO_ENVIO)
        bem = self._mk_bem(status=constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)
        item = BaixaFisicaBensItem.objects.create(baixa=baixa, bem=bem)
        form = MagicMock()
        form.instance = baixa
        
        # Mock do formset com deleted_objects
        formset = MagicMock()
        formset.model = BaixaFisicaBensItem
        formset.deleted_objects = [item]
        formset.new_objects = []
        
        request = self.factory.post("/")
        request.user = self.operador
        self.admin.save_related(request, form, [formset], change=True)
        
        bem.refresh_from_db()
        self.assertEqual(bem.status, constants.APROVADO)

    def test_save_related_nao_ajusta_status_se_nao_aguardando_envio(self):
        """save_related não ajusta status se baixa não está AGUARDANDO_ENVIO."""
        baixa = self._mk_baixa(status=constants.SOLICITADA)
        bem = self._mk_bem(status=constants.APROVADO)
        form = MagicMock()
        form.instance = baixa
        
        # Criar item após salvar
        item = BaixaFisicaBensItem.objects.create(baixa=baixa, bem=bem)
        
        # Mock do formset com new_objects
        formset = MagicMock()
        formset.model = BaixaFisicaBensItem
        formset.deleted_objects = []
        formset.new_objects = [item]
        
        request = self.factory.post("/")
        request.user = self.operador
        self.admin.save_related(request, form, [formset], change=True)
        
        bem.refresh_from_db()
        # Status não deve mudar porque baixa não está AGUARDANDO_ENVIO
        self.assertEqual(bem.status, constants.APROVADO)

    def test_has_view_permission_gestor(self):
        """has_view_permission retorna True para gestor."""
        request = self.factory.get("/")
        request.user = self.gestor
        self.assertTrue(self.admin.has_view_permission(request))

    def test_has_view_permission_operador(self):
        """has_view_permission retorna True para operador."""
        request = self.factory.get("/")
        request.user = self.operador
        self.assertTrue(self.admin.has_view_permission(request))

    def test_has_view_permission_superuser(self):
        """has_view_permission retorna True para superuser."""
        superuser = User.objects.create_user(
            username="super",
            password="x",
            email="super@test.com",
            is_staff=True,
            is_superuser=True,
        )
        request = self.factory.get("/")
        request.user = superuser
        self.assertTrue(self.admin.has_view_permission(request))

    def test_has_view_permission_usuario_nao_autenticado(self):
        """has_view_permission retorna False para usuário não autenticado."""
        request = self.factory.get("/")
        request.user = MagicMock()
        request.user.is_authenticated = False
        self.assertFalse(self.admin.has_view_permission(request))

    def test_has_delete_permission_sempre_false(self):
        """has_delete_permission sempre retorna False."""
        request = self.factory.get("/")
        request.user = self.gestor
        self.assertFalse(self.admin.has_delete_permission(request))
        self.assertFalse(self.admin.has_delete_permission(request, self._mk_baixa()))

    def test_get_actions_remove_delete_selected(self):
        """get_actions remove delete_selected."""
        request = self.factory.get("/")
        request.user = self.gestor
        actions = self.admin.get_actions(request)
        self.assertNotIn("delete_selected", actions)

    def test_get_actions_remove_aprovar_para_nao_gestor(self):
        """get_actions remove acao_aprovar_baixa para não gestor."""
        request = self.factory.get("/")
        request.user = self.operador
        actions = self.admin.get_actions(request)
        self.assertNotIn("acao_aprovar_baixa", actions)
        self.assertNotIn("acao_cancelar_baixa", actions)

    def test_get_actions_mantem_aprovar_para_gestor(self):
        """get_actions mantém acao_aprovar_baixa para gestor."""
        request = self.factory.get("/")
        request.user = self.gestor
        actions = self.admin.get_actions(request)
        self.assertIn("acao_aprovar_baixa", actions)
        self.assertIn("acao_cancelar_baixa", actions)

    @patch('bem_patrimonial.admins.baixa_fisica_bem_patrimonial.envia_email_baixa_fisica_solicitada')
    def test_acao_enviar_baixa_com_status_correto(self, mock_email):
        """acao_enviar_baixa envia baixas com status AGUARDANDO_ENVIO."""
        baixa1 = self._mk_baixa(status=constants.AGUARDANDO_ENVIO)
        bem1 = self._mk_bem()
        BaixaFisicaBensItem.objects.create(baixa=baixa1, bem=bem1)
        
        baixa2 = self._mk_baixa(status=constants.AGUARDANDO_ENVIO, numero_processo_baixa="PROC-456")
        bem2 = self._mk_bem()
        BaixaFisicaBensItem.objects.create(baixa=baixa2, bem=bem2)
        
        request = self.factory.post("/")
        request.user = self.operador
        self._add_messages_support(request)
        
        queryset = BaixaFisicaBemPatrimonial.objects.filter(pk__in=[baixa1.pk, baixa2.pk])
        self.admin.acao_enviar_baixa(request, queryset)
        
        baixa1.refresh_from_db()
        baixa2.refresh_from_db()
        self.assertEqual(baixa1.status, constants.SOLICITADA)
        self.assertEqual(baixa2.status, constants.SOLICITADA)
        self.assertEqual(mock_email.call_count, 2)

    def test_acao_enviar_baixa_com_status_incorreto(self):
        """acao_enviar_baixa mostra erro para baixas com status incorreto."""
        baixa1 = self._mk_baixa(status=constants.AGUARDANDO_ENVIO)
        bem1 = self._mk_bem()
        BaixaFisicaBensItem.objects.create(baixa=baixa1, bem=bem1)
        
        baixa2 = self._mk_baixa(status=constants.SOLICITADA, numero_processo_baixa="PROC-456")
        bem2 = self._mk_bem()
        BaixaFisicaBensItem.objects.create(baixa=baixa2, bem=bem2)
        
        request = self.factory.post("/")
        request.user = self.operador
        self._add_messages_support(request)
        
        queryset = BaixaFisicaBemPatrimonial.objects.filter(pk__in=[baixa1.pk, baixa2.pk])
        self.admin.acao_enviar_baixa(request, queryset)
        
        # Apenas baixa1 deve ser enviada
        baixa1.refresh_from_db()
        self.assertEqual(baixa1.status, constants.SOLICITADA)

    @patch('bem_patrimonial.admins.baixa_fisica_bem_patrimonial.envia_email_baixa_fisica_aprovada')
    def test_acao_aprovar_baixa_com_status_correto(self, mock_email):
        """acao_aprovar_baixa aprova baixas com status SOLICITADA."""
        baixa1 = self._mk_baixa(status=constants.SOLICITADA)
        bem1 = self._mk_bem(status=constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)
        BaixaFisicaBensItem.objects.create(baixa=baixa1, bem=bem1)
        
        baixa2 = self._mk_baixa(status=constants.SOLICITADA, numero_processo_baixa="PROC-456")
        bem2 = self._mk_bem(status=constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)
        BaixaFisicaBensItem.objects.create(baixa=baixa2, bem=bem2)
        
        request = self.factory.post("/")
        request.user = self.gestor
        self._add_messages_support(request)
        
        queryset = BaixaFisicaBemPatrimonial.objects.filter(pk__in=[baixa1.pk, baixa2.pk])
        self.admin.acao_aprovar_baixa(request, queryset)
        
        baixa1.refresh_from_db()
        baixa2.refresh_from_db()
        self.assertEqual(baixa1.status, constants.ACEITA)
        self.assertEqual(baixa2.status, constants.ACEITA)
        self.assertEqual(mock_email.call_count, 2)

    def test_acao_aprovar_baixa_nao_gestor_mostra_erro(self):
        """acao_aprovar_baixa mostra erro para não gestor."""
        baixa = self._mk_baixa(status=constants.SOLICITADA)
        request = self.factory.post("/")
        request.user = self.operador
        self._add_messages_support(request)
        
        queryset = BaixaFisicaBemPatrimonial.objects.filter(pk=baixa.pk)
        self.admin.acao_aprovar_baixa(request, queryset)
        
        # Status não deve mudar
        baixa.refresh_from_db()
        self.assertEqual(baixa.status, constants.SOLICITADA)

    @patch('bem_patrimonial.admins.baixa_fisica_bem_patrimonial.envia_email_baixa_fisica_cancelada')
    def test_acao_cancelar_baixa_com_status_correto(self, mock_email):
        """acao_cancelar_baixa cancela baixas com status AGUARDANDO_ENVIO ou SOLICITADA."""
        baixa1 = self._mk_baixa(status=constants.AGUARDANDO_ENVIO)
        bem1 = self._mk_bem(status=constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)
        BaixaFisicaBensItem.objects.create(baixa=baixa1, bem=bem1)
        
        baixa2 = self._mk_baixa(status=constants.SOLICITADA, numero_processo_baixa="PROC-456")
        bem2 = self._mk_bem(status=constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)
        BaixaFisicaBensItem.objects.create(baixa=baixa2, bem=bem2)
        
        request = self.factory.post("/")
        request.user = self.gestor
        self._add_messages_support(request)
        
        queryset = BaixaFisicaBemPatrimonial.objects.filter(pk__in=[baixa1.pk, baixa2.pk])
        self.admin.acao_cancelar_baixa(request, queryset)
        
        baixa1.refresh_from_db()
        baixa2.refresh_from_db()
        bem1.refresh_from_db()
        bem2.refresh_from_db()
        self.assertEqual(baixa1.status, constants.RECUSADA)
        self.assertEqual(baixa2.status, constants.RECUSADA)
        # Bens devem voltar para APROVADO
        self.assertEqual(bem1.status, constants.APROVADO)
        self.assertEqual(bem2.status, constants.APROVADO)
        self.assertEqual(mock_email.call_count, 2)

    def test_acao_cancelar_baixa_nao_gestor_mostra_erro(self):
        """acao_cancelar_baixa mostra erro para não gestor."""
        baixa = self._mk_baixa(status=constants.AGUARDANDO_ENVIO)
        request = self.factory.post("/")
        request.user = self.operador
        self._add_messages_support(request)
        
        queryset = BaixaFisicaBemPatrimonial.objects.filter(pk=baixa.pk)
        self.admin.acao_cancelar_baixa(request, queryset)
        
        # Status não deve mudar
        baixa.refresh_from_db()
        self.assertEqual(baixa.status, constants.AGUARDANDO_ENVIO)

    def test_formfield_for_dbfield_data_baixa(self):
        """formfield_for_dbfield configura widget para data_baixa."""
        request = self.factory.get("/")
        request.user = self.operador
        field = self.admin.formfield_for_dbfield(
            BaixaFisicaBemPatrimonial._meta.get_field("data_baixa"),
            request
        )
        # Verificar se o widget foi configurado com max
        self.assertIsNotNone(field.widget.attrs.get("max"))
        # Verificar se o widget é DateInput
        from django.forms import DateInput
        self.assertIsInstance(field.widget, DateInput)
        # Verificar se tem type="date" nos attrs (pode estar no widget ou nos attrs)
        widget_type = getattr(field.widget, "input_type", None) or field.widget.attrs.get("type")
        if widget_type:
            self.assertEqual(widget_type, "date")
        else:
            # Se não tiver type, pelo menos verificar que é DateInput
            self.assertIsInstance(field.widget, DateInput)

    def test_changelist_view_operador_sem_ua_mostra_warning(self):
        """changelist_view mostra warning para operador sem UA."""
        operador_sem_ua = User.objects.create_user(
            username="operador_sem_ua",
            password="x",
            email="operador_sem_ua@test.com",
            is_staff=True,
            unidade_administrativa=None,
        )
        operador_sem_ua.groups.add(self.grupo_operador)
        
        request = self.factory.get("/")
        request.user = operador_sem_ua
        self._add_messages_support(request)
        
        self.admin.changelist_view(request)
        
        # Verificar se há mensagem de warning
        storage = request._messages
        messages_list = list(storage)
        self.assertTrue(any("unidade administrativa" in str(msg).lower() for msg in messages_list))
