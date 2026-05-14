from types import SimpleNamespace
from unittest.mock import patch

from django.test import Client
from django.forms import modelform_factory
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase
from django.urls import reverse

from bem_patrimonial.admins.inlines.inlines import (
    TransferenciaBensItemInline,
    TransferenciaBensItemInlineForm,
    TransferenciaBensItemInlineFormSet,
)
from bem_patrimonial.admins.transferencia_bem_patrimonial import (
    TransferenciaBemPatrimonialAdmin,
)
from bem_patrimonial.admins.forms.transferencia_bem_patrimonial_form import (
    TransferenciaBemPatrimonialForm,
)
from bem_patrimonial import constants
from bem_patrimonial.models import (
    BemPatrimonial,
    TransferenciaBemPatrimonial,
    TransferenciaBensItem,
)
from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua, codigo_uo
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario


class TransferenciaBemPatrimonialAdminTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = TransferenciaBemPatrimonialAdmin(
            TransferenciaBemPatrimonial,
            self.site,
        )

        self.uo_origem = criar_uo(codigo=codigo_uo(1, 16, 70), nome="SME", sigla="SME")
        self.ua_origem = criar_ua(
            uo=self.uo_origem,
            codigo=f"{self.uo_origem.codigo}.001",
            sigla="UA1",
            nome="Unidade 1",
        )
        self.ua_origem_2 = criar_ua(
            uo=self.uo_origem,
            codigo=f"{self.uo_origem.codigo}.002",
            sigla="UA2",
            nome="Unidade 2",
        )
        self.uo_destino = criar_uo(
            codigo=codigo_uo(3, 30, 30),
            nome="Secretaria Externa",
            sigla="EXT",
        )
        self.ua_destino = criar_ua(
            uo=self.uo_destino,
            codigo=codigo_ua(3, 30, 30, 1),
            sigla="PC",
            nome="Ponto Central",
        )
        self.ua_destino_2 = criar_ua(
            uo=self.uo_destino,
            codigo=codigo_ua(3, 30, 30, 2),
            sigla="DST2",
            nome="Destino 2",
        )

        grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        grupo_operador = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)[0]

        self.gestor = Usuario.objects.create_user(
            username="gestor_transfer_admin",
            email="gestor.transfer.admin@test.com",
            **auth_kwargs("123456"),
            nome="Gestor",
            is_staff=True,
            unidade_orcamentaria=self.uo_origem,
            unidade_administrativa=self.ua_origem,
        )
        self.gestor.groups.add(grupo_gestor)
        self.gestor.must_change_password = False
        self.gestor.save(update_fields=["must_change_password"])

        self.gestor_destino = Usuario.objects.create_user(
            username="gestor_transfer_destino",
            email="gestor.transfer.destino@test.com",
            **auth_kwargs("123456"),
            nome="Gestor Destino",
            is_staff=True,
            unidade_orcamentaria=self.uo_destino,
            unidade_administrativa=self.ua_destino_2,
        )
        self.gestor_destino.groups.add(grupo_gestor)

        self.operador = Usuario.objects.create_user(
            username="operador_transfer_admin",
            email="operador.transfer.admin@test.com",
            **auth_kwargs("123456"),
            nome="Operador",
            is_staff=True,
            unidade_orcamentaria=self.uo_origem,
            unidade_administrativa=self.ua_origem,
        )
        self.operador.groups.add(grupo_operador)

    def test_form_resolve_ua_destino_001_automaticamente(self):
        form = TransferenciaBemPatrimonialForm(
            data={
                "unidade_orcamentaria_destino": self.uo_destino.pk,
                "numero_processo": "SEI-123/2026",
                "observacao": "Teste",
            },
            request=type("obj", (object,), {"user": self.gestor})(),
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(
            form.cleaned_data["unidade_orcamentaria_origem"],
            self.uo_origem,
        )
        self.assertEqual(
            form.cleaned_data["unidade_administrativa_destino"],
            self.ua_destino,
        )

    def test_form_expoe_filtro_por_ua_da_uo_origem(self):
        form = TransferenciaBemPatrimonialForm(
            request=type("obj", (object,), {"user": self.gestor})(),
        )

        queryset = form.fields["unidade_administrativa_filtro"].queryset
        self.assertEqual(
            list(queryset.values_list("id", flat=True)),
            [self.ua_origem.id, self.ua_origem_2.id],
        )

    def test_change_form_nao_quebra_quando_campos_model_sao_readonly(self):
        transferencia = TransferenciaBemPatrimonial.objects.create(
            unidade_orcamentaria_origem=self.uo_origem,
            unidade_orcamentaria_destino=self.uo_destino,
            unidade_administrativa_destino=self.ua_destino,
            numero_processo="SEI-123/2026",
            criado_por=self.gestor,
        )
        request = self.factory.get(
            f"/admin/bem_patrimonial/transferenciabempatrimonial/{transferencia.pk}/change/"
        )
        request.user = self.gestor

        form_class = self.admin.get_form(request, obj=transferencia)
        form = form_class(instance=transferencia)

        self.assertNotIn("unidade_orcamentaria_origem", form.fields)

    def test_queryset_admin_exibe_transferencia_para_uo_destino(self):
        transferencia = TransferenciaBemPatrimonial.objects.create(
            unidade_orcamentaria_origem=self.uo_origem,
            unidade_orcamentaria_destino=self.uo_destino,
            unidade_administrativa_destino=self.ua_destino,
            numero_processo="SEI-123/2026",
            criado_por=self.gestor,
        )
        request = self.factory.get("/admin/bem_patrimonial/transferenciabempatrimonial/")
        request.user = self.gestor_destino

        queryset = self.admin.get_queryset(request)

        self.assertIn(transferencia, queryset)

    def test_change_form_remove_bloco_redundante_bens_transferidos(self):
        request = self.factory.get("/admin/bem_patrimonial/transferenciabempatrimonial/1/change/")
        request.user = self.gestor

        fields = self.admin.get_fields(
            request,
            obj=TransferenciaBemPatrimonial(
                unidade_orcamentaria_origem=self.uo_origem,
                unidade_orcamentaria_destino=self.uo_destino,
                unidade_administrativa_destino=self.ua_destino,
                numero_processo="SEI-123/2026",
                criado_por=self.gestor,
            ),
        )

        self.assertNotIn("get_bens_transferidos_links", fields)

    def test_create_form_posiciona_filtro_perto_dos_itens(self):
        request = self.factory.get("/admin/bem_patrimonial/transferenciabempatrimonial/add/")
        request.user = self.gestor

        fields = self.admin.get_fields(request)

        self.assertEqual(fields[-1], "unidade_administrativa_filtro")

    def test_inline_formset_exige_ao_menos_um_bem(self):
        formset = TransferenciaBensItemInlineFormSet.__new__(
            TransferenciaBensItemInlineFormSet
        )
        formset.forms = [SimpleNamespace(cleaned_data={"bem": None, "DELETE": False})]
        formset._errors = []

        with patch("django.forms.models.BaseInlineFormSet.clean", return_value=None):
            with self.assertRaises(ValidationError) as ctx:
                formset.clean()

        self.assertIn("ao menos um bem", str(ctx.exception))

    def test_inline_formset_ignora_validacao_quando_ha_erros(self):
        formset = TransferenciaBensItemInlineFormSet.__new__(
            TransferenciaBensItemInlineFormSet
        )
        formset.forms = []
        formset._errors = [{"bem": ["erro"]}]

        with patch("django.forms.models.BaseInlineFormSet.clean", return_value=None):
            formset.clean()

    def test_inline_form_personaliza_label_do_bem(self):
        form = TransferenciaBensItemInlineForm()
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000091-0",
            nome="Bem label inline",
            descricao="Descricao",
            valor_unitario=100,
            marca="Marca",
            modelo="Modelo",
            numero_processo="PROC-2",
            status=constants.APROVADO,
            unidade_administrativa=self.ua_origem,
            criado_por=self.gestor,
        )

        label = form.fields["bem"].label_from_instance(bem)

        self.assertIn(f"{self.ua_origem.codigo} - {self.ua_origem.sigla}", label)
        self.assertIn("001.000000091-0", label)
        self.assertIn("Bem label inline", label)

    def test_inline_form_nao_quebra_sem_campo_bem_no_change_view(self):
        form_class = modelform_factory(
            TransferenciaBensItem,
            form=TransferenciaBensItemInlineForm,
            fields=(),
        )

        form = form_class()

        self.assertNotIn("bem", form.fields)

    def test_inline_change_view_exibe_ua_e_link_do_bem(self):
        transferencia = TransferenciaBemPatrimonial.objects.create(
            unidade_orcamentaria_origem=self.uo_origem,
            unidade_orcamentaria_destino=self.uo_destino,
            unidade_administrativa_destino=self.ua_destino,
            numero_processo="SEI-123/2026",
            criado_por=self.gestor,
        )
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000092-0",
            nome="Bem detalhado inline",
            descricao="Descricao",
            valor_unitario=100,
            marca="Marca",
            modelo="Modelo",
            numero_processo="PROC-3",
            status=constants.APROVADO,
            unidade_administrativa=self.ua_origem_2,
            criado_por=self.gestor,
        )
        item = TransferenciaBensItem.objects.create(transferencia=transferencia, bem=bem)
        transferencia.efetivar_transferencia(self.gestor)
        item.refresh_from_db()
        inline = TransferenciaBensItemInline(TransferenciaBemPatrimonial, self.site)

        html = inline.bem_detalhado(item)

        self.assertIn(f"{self.ua_origem_2.codigo} - {self.ua_origem_2.sigla}", html)
        self.assertIn("001.000000092-0 - Bem detalhado inline", html)
        self.assertNotIn(str(self.ua_destino), html)
        self.assertIn(
            reverse("admin:bem_patrimonial_bempatrimonial_change", args=[bem.pk]),
            html,
        )

    def test_inline_nao_permita_exclusao(self):
        inline = TransferenciaBensItemInline(TransferenciaBemPatrimonial, self.site)

        self.assertFalse(inline.can_delete)

    def test_change_view_nao_exibe_texto_original_nem_controles_de_apagar(self):
        transferencia = TransferenciaBemPatrimonial.objects.create(
            unidade_orcamentaria_origem=self.uo_origem,
            unidade_orcamentaria_destino=self.uo_destino,
            unidade_administrativa_destino=self.ua_destino,
            numero_processo="SEI-HTML-1",
            criado_por=self.gestor,
        )
        bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000093-0",
            nome="Bem template inline",
            descricao="Descricao",
            valor_unitario=100,
            marca="Marca",
            modelo="Modelo",
            numero_processo="PROC-HTML-1",
            status=constants.APROVADO,
            unidade_administrativa=self.ua_origem_2,
            criado_por=self.gestor,
        )
        TransferenciaBensItem.objects.create(transferencia=transferencia, bem=bem)

        client = Client()
        client.force_login(self.gestor)
        response = client.get(
            reverse(
                "admin:bem_patrimonial_transferenciabempatrimonial_change",
                args=[transferencia.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Transf#")
        self.assertNotContains(response, "Apagar?")
        self.assertNotContains(response, "deletelink")

    def test_changeform_extra_context_oculta_botoes_de_salvar(self):
        context = self.admin._get_changeform_extra_context(object_id="1")

        self.assertFalse(context["show_save"])
        self.assertFalse(context["show_save_and_continue"])
        self.assertFalse(context["show_save_and_add_another"])
        self.assertTrue(context["show_close"])

    def test_change_view_rejeita_post_em_registro_existente(self):
        request = self.factory.post("/admin/bem_patrimonial/transferenciabempatrimonial/1/change/")
        request.user = self.gestor

        with self.assertRaises(PermissionDenied):
            self.admin.changeform_view(request, object_id="1")

    def test_inline_has_add_permission_apenas_na_criacao(self):
        inline = TransferenciaBensItemInline(TransferenciaBemPatrimonial, self.site)
        request = self.factory.get("/admin/")
        request.user = self.gestor

        self.assertTrue(inline.has_add_permission(request, obj=None))
        self.assertFalse(
            inline.has_add_permission(
                request,
                obj=TransferenciaBemPatrimonial(
                    unidade_orcamentaria_origem=self.uo_origem,
                    unidade_orcamentaria_destino=self.uo_destino,
                    unidade_administrativa_destino=self.ua_destino,
                    numero_processo="SEI-OBJ",
                    criado_por=self.gestor,
                ),
            )
        )

    def test_admin_modulo_restrito_a_gestor(self):
        request_gestor = self.factory.get("/admin/bem_patrimonial/transferenciabempatrimonial/")
        request_gestor.user = self.gestor

        request_operador = self.factory.get("/admin/bem_patrimonial/transferenciabempatrimonial/")
        request_operador.user = self.operador

        self.assertTrue(self.admin.has_module_permission(request_gestor))
        self.assertTrue(self.admin.has_view_permission(request_gestor))
        self.assertFalse(self.admin.has_module_permission(request_operador))
        self.assertFalse(self.admin.has_view_permission(request_operador))