
from datetime import date
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO
from usuario.models import Usuario

from inventario.forms import ConciliacaoUAAdminForm
from inventario.models import ConciliacaoUA, ParametroConciliacaoAnual
from inventario import constants


class ConciliacaoUAAdminFormTestBase(TestCase):
    """Base com dados mínimos para cobrir o form (banco de teste)."""

    def setUp(self):
        self.uo = criar_uo(codigo="100", nome="UO Teste")
        self.ua = criar_ua(
            uo=self.uo,
            codigo="01.16.10.379",
            sigla="UA_A",
            nome="Unidade A",
            status=UnidadeAdministrativa.ATIVA,
        )
        self.ua_outra = criar_ua(
            uo=self.uo,
            codigo="01.16.10.408",
            sigla="UA_B",
            nome="Unidade B",
            status=UnidadeAdministrativa.ATIVA,
        )
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.usuario_com_ua = Usuario.objects.create_user(
            username="user_ua",
            password="x",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.usuario_com_ua.groups.add(grupo_gestor)


class TestConciliacaoUAAdminFormInit(ConciliacaoUAAdminFormTestBase):

    def test_init_pop_request_from_kwargs(self):
        request = MagicMock()
        request.user = None
        form = ConciliacaoUAAdminForm(request=request)
        self.assertIs(form.request, request)

    def test_init_sem_request_user_none(self):
        form = ConciliacaoUAAdminForm()
        self.assertIsNone(getattr(form.request, "user", None))

    def test_init_nova_instancia_define_tipo_eventual_e_disabled(self):
        form = ConciliacaoUAAdminForm()
        self.assertEqual(
            list(form.fields["tipo"].choices),
            [(constants.CONCILIACAO_EVENTUAL, "Eventual")],
        )
        self.assertEqual(form.fields["tipo"].initial, constants.CONCILIACAO_EVENTUAL)
        self.assertTrue(form.fields["tipo"].disabled)

    def test_init_campos_required(self):
        form = ConciliacaoUAAdminForm()
        self.assertTrue(form.fields["unidade_administrativa"].required)
        self.assertTrue(form.fields["tipo"].required)
        self.assertFalse(form.fields["periodo_final"].required)

    def test_init_com_user_define_queryset_unidade_administrativa(self):
        request = MagicMock()
        request.user = self.usuario_com_ua
        form = ConciliacaoUAAdminForm(request=request)
        qs = form.fields["unidade_administrativa"].queryset
        self.assertIn(self.ua, qs)

    def test_init_com_user_ua_ativa_nao_super_admin_fixa_ua_e_disabled(self):
        request = MagicMock()
        request.user = self.usuario_com_ua
        form = ConciliacaoUAAdminForm(request=request)
        self.assertEqual(form.fields["unidade_administrativa"].initial, self.ua)
        self.assertTrue(form.fields["unidade_administrativa"].disabled)

    def test_init_instancia_com_pk_desabilita_todos_os_campos(self):
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario_com_ua,
        )
        form = ConciliacaoUAAdminForm(instance=conciliacao)
        self.assertTrue(form.fields["unidade_administrativa"].disabled)
        self.assertTrue(form.fields["tipo"].disabled)
        self.assertTrue(form.fields["periodo_final"].disabled)


class TestConciliacaoUAAdminFormClean(ConciliacaoUAAdminFormTestBase):

    def test_clean_sem_tipo_erro(self):
        form = ConciliacaoUAAdminForm()
        form.request = None
        form.cleaned_data = {"unidade_administrativa": self.ua, "periodo_final": timezone.localdate()}
        with self.assertRaises(ValidationError) as ctx:
            form.clean()
        self.assertIn("tipo", ctx.exception.message_dict)

    def test_clean_sem_unidade_administrativa_erro(self):
        form = ConciliacaoUAAdminForm(data={
            "tipo": constants.CONCILIACAO_EVENTUAL,
            "periodo_final": timezone.localdate(),
        })
        form.request = None
        self.assertFalse(form.is_valid())
        self.assertIn("unidade_administrativa", form.errors)

    def test_clean_com_user_ua_fora_do_escopo_erro(self):
        uo_outra = criar_uo(codigo="999", nome="UO Outra")
        criar_ua(
            uo=uo_outra,
            codigo="99.99.99.999",
            sigla="OUTRA",
            nome="UA Outra UO",
            status=UnidadeAdministrativa.ATIVA,
        )
        user_outra_uo = Usuario.objects.create_user(
            username="user_outra_uo",
            password="x",
            unidade_administrativa=None,
            unidade_orcamentaria=uo_outra,
        )
        user_outra_uo.groups.add(Group.objects.get(name=GRUPO_GESTOR_PATRIMONIO))
        request = MagicMock()
        request.user = user_outra_uo
        form = ConciliacaoUAAdminForm(
            data={
                "unidade_administrativa": self.ua.pk,
                "tipo": constants.CONCILIACAO_EVENTUAL,
                "periodo_final": timezone.localdate(),
            },
            request=request,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("unidade_administrativa", form.errors)
        msg = form.errors["unidade_administrativa"][0]
        self.assertTrue("permissão" in msg or "escolha válida" in msg or "disponíveis" in msg)

    def test_clean_com_user_ua_ativa_sobrescreve_cleaned_para_ua_user(self):
        request = MagicMock()
        request.user = self.usuario_com_ua
        form = ConciliacaoUAAdminForm(
            data={
                "unidade_administrativa": self.ua.pk,
                "tipo": constants.CONCILIACAO_EVENTUAL,
                "periodo_final": timezone.localdate(),
            },
            request=request,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_clean_nova_conciliacao_quando_ja_existe_em_aberto_erro(self):
        ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario_com_ua,
        )
        form = ConciliacaoUAAdminForm(
            data={
                "unidade_administrativa": self.ua.pk,
                "tipo": constants.CONCILIACAO_EVENTUAL,
                "periodo_final": timezone.localdate(),
            },
        )
        form.request = None
        self.assertFalse(form.is_valid())
        self.assertIn("unidade_administrativa", form.errors)
        self.assertIn("em aberto", form.errors["unidade_administrativa"][0])

    def test_clean_tipo_eventual_sem_periodo_final_erro(self):
        form = ConciliacaoUAAdminForm(
            data={
                "unidade_administrativa": self.ua.pk,
                "tipo": constants.CONCILIACAO_EVENTUAL,
                "periodo_final": "",
            },
        )
        form.request = None
        self.assertFalse(form.is_valid())
        self.assertIn("periodo_final", form.errors)

    def test_clean_tipo_eventual_com_periodo_final_ok(self):
        form = ConciliacaoUAAdminForm(
            data={
                "unidade_administrativa": self.ua.pk,
                "tipo": constants.CONCILIACAO_EVENTUAL,
                "periodo_final": timezone.localdate(),
            },
        )
        form.request = None
        self.assertTrue(form.is_valid(), form.errors)

    @patch("inventario.forms.timezone")
    def test_clean_tipo_anual_dentro_periodo_parametro_ok(self, mock_tz):
        hoje = date(2026, 2, 15)
        mock_tz.localdate.return_value = hoje
        ParametroConciliacaoAnual.objects.create(
            ano_referencia=2025,
            periodo_inicial=date(2026, 1, 1),
            periodo_final=date(2026, 3, 31),
            ativo=True,
            unidade_orcamentaria=self.uo,
        )
        form = ConciliacaoUAAdminForm(
            data={
                "unidade_administrativa": self.ua.pk,
                "tipo": constants.CONCILIACAO_ANUAL,
                "periodo_final": "",
            },
        )
        form.request = None
        form.fields["tipo"].choices = [
            (constants.CONCILIACAO_ANUAL, "Anual"),
            (constants.CONCILIACAO_EVENTUAL, "Eventual"),
        ]
        form.fields["tipo"].initial = None
        form.fields["tipo"].disabled = False
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["periodo_final"], date(2025, 12, 31))

    @patch("inventario.forms.timezone")
    def test_clean_tipo_anual_fora_periodo_parametro_erro(self, mock_tz):
        hoje = date(2026, 5, 1)
        mock_tz.localdate.return_value = hoje
        ParametroConciliacaoAnual.objects.create(
            ano_referencia=2025,
            periodo_inicial=date(2026, 1, 1),
            periodo_final=date(2026, 3, 31),
            ativo=True,
            unidade_orcamentaria=self.uo,
        )
        form = ConciliacaoUAAdminForm(
            data={
                "unidade_administrativa": self.ua.pk,
                "tipo": constants.CONCILIACAO_ANUAL,
                "periodo_final": "",
            },
        )
        form.request = None
        form.fields["tipo"].choices = [
            (constants.CONCILIACAO_ANUAL, "Anual"),
            (constants.CONCILIACAO_EVENTUAL, "Eventual"),
        ]
        form.fields["tipo"].disabled = False
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

    @patch("inventario.forms.timezone")
    def test_clean_tipo_anual_sem_parametro_fora_jan_mar_erro(self, mock_tz):
        hoje = date(2026, 6, 1)
        mock_tz.localdate.return_value = hoje
        form = ConciliacaoUAAdminForm(
            data={
                "unidade_administrativa": self.ua.pk,
                "tipo": constants.CONCILIACAO_ANUAL,
                "periodo_final": "",
            },
        )
        form.request = None
        form.fields["tipo"].choices = [
            (constants.CONCILIACAO_ANUAL, "Anual"),
            (constants.CONCILIACAO_EVENTUAL, "Eventual"),
        ]
        form.fields["tipo"].disabled = False
        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)
