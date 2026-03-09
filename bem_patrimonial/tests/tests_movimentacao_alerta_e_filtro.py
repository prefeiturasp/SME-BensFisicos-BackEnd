from dados_comuns.tests.auth_test_utils import auth_kwargs
from datetime import timedelta

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from bem_patrimonial.admins.filters.movimentacao_filters import (
    MovimentacaoAtrasadaFilter,
)
from bem_patrimonial import constants
from bem_patrimonial.models import MovimentacaoBemPatrimonial
from bem_patrimonial.templatetags.movimentacoes_pendentes_tags import (
    alerta_movimentacoes_pendentes,
)
from dados_comuns.tests.factories import criar_ua
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario


class AlertaMovimentacoesPendentesTagTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.ua_origem = criar_ua(nome="UA Origem", codigo="00.00.00.100", sigla="UA-O")
        self.ua_destino = criar_ua(
            uo=self.ua_origem.unidade_orcamentaria,
            nome="UA Destino",
            codigo="00.00.00.200",
            sigla="UA-D",
        )
        grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
        self.usuario = Usuario.objects.create_user(
            username="operador",
            **auth_kwargs("test123"),
            unidade_administrativa=self.ua_destino,
            unidade_orcamentaria=self.ua_destino.unidade_orcamentaria,
        )
        self.usuario.groups.add(grupo_operador)
        self.usuario.unidades_administrativas.add(self.ua_destino)

    def _cria_movimentacao(self, dias_atraso=8):
        mov = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.usuario,
        )
        MovimentacaoBemPatrimonial.objects.filter(pk=mov.pk).update(
            criado_em=timezone.now() - timedelta(days=dias_atraso)
        )
        return mov

    def test_tag_sem_request(self):
        resultado = alerta_movimentacoes_pendentes({})
        self.assertIsNone(resultado["pendencias"])

    def test_tag_usuario_sem_ua(self):
        usuario = Usuario.objects.create_user(username="sem_ua", **auth_kwargs("test123"))
        request = self.factory.get("/")
        request.user = usuario
        resultado = alerta_movimentacoes_pendentes({"request": request})
        self.assertIsNone(resultado["pendencias"])

    def test_tag_superuser_sem_ua(self):
        usuario = Usuario.objects.create_user(
            username="super", **auth_kwargs("test123"), is_superuser=True
        )
        request = self.factory.get("/")
        request.user = usuario
        resultado = alerta_movimentacoes_pendentes({"request": request})
        self.assertIsNone(resultado["pendencias"])

    def test_tag_gestor_sem_ua(self):
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        usuario = Usuario.objects.create_user(username="gestor", **auth_kwargs("test123"))
        usuario.groups.add(grupo_gestor)
        request = self.factory.get("/")
        request.user = usuario
        resultado = alerta_movimentacoes_pendentes({"request": request})
        self.assertIsNone(resultado["pendencias"])

    def test_tag_usuario_sem_grupo(self):
        usuario = Usuario.objects.create_user(
            username="sem_grupo",
            **auth_kwargs("test123"),
            unidade_administrativa=self.ua_destino,
            unidade_orcamentaria=self.ua_destino.unidade_orcamentaria,
        )
        request = self.factory.get("/")
        request.user = usuario
        resultado = alerta_movimentacoes_pendentes({"request": request})
        self.assertIsNone(resultado["pendencias"])

    def test_tag_sem_pendencias(self):
        request = self.factory.get("/")
        request.user = self.usuario
        resultado = alerta_movimentacoes_pendentes({"request": request})
        self.assertIsNone(resultado["pendencias"])

    def test_tag_pendencias_menos_7_dias(self):
        self._cria_movimentacao(dias_atraso=3)
        request = self.factory.get("/")
        request.user = self.usuario
        resultado = alerta_movimentacoes_pendentes({"request": request})
        self.assertIsNone(resultado["pendencias"])

    def test_tag_com_pendencias(self):
        self._cria_movimentacao(dias_atraso=8)
        request = self.factory.get("/")
        request.user = self.usuario
        resultado = alerta_movimentacoes_pendentes({"request": request}, css_class="x")
        self.assertIsNotNone(resultado["pendencias"])
        self.assertEqual(resultado["pendencias"]["total"], 1)
        expected_url = (
            reverse("admin:bem_patrimonial_movimentacaobempatrimonial_changelist")
            + "?atrasada=1"
        )
        self.assertEqual(resultado["pendencias"]["url"], expected_url)
        self.assertEqual(resultado["css_class"], "x")


class MovimentacaoAtrasadaFilterTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.ua_origem = criar_ua(nome="UA Origem", codigo="00.00.00.101", sigla="UA-O")
        self.ua_destino = criar_ua(
            uo=self.ua_origem.unidade_orcamentaria,
            nome="UA Destino",
            codigo="00.00.00.201",
            sigla="UA-D",
        )
        self.usuario = Usuario.objects.create_user(
            username="operador2",
            **auth_kwargs("test123"),
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.ua_origem.unidade_orcamentaria,
        )
        self.model_admin = admin.ModelAdmin(MovimentacaoBemPatrimonial, AdminSite())

    def _cria_movimentacao(self, dias_atraso):
        mov = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.usuario,
            status=constants.ENVIADA,
        )
        MovimentacaoBemPatrimonial.objects.filter(pk=mov.pk).update(
            criado_em=timezone.now() - timedelta(days=dias_atraso)
        )
        return mov

    def test_filter_aplica_atraso(self):
        mov_atrasada = self._cria_movimentacao(dias_atraso=8)
        mov_recente = self._cria_movimentacao(dias_atraso=2)

        request = self.factory.get("/admin", {"atrasada": "1"})
        filtro = MovimentacaoAtrasadaFilter(
            request, {"atrasada": "1"}, MovimentacaoBemPatrimonial, self.model_admin
        )
        qs = filtro.queryset(request, MovimentacaoBemPatrimonial.objects.all())

        self.assertIn(mov_atrasada, qs)
        self.assertNotIn(mov_recente, qs)

    def test_filter_exclui_status_nao_enviada(self):
        mov_atrasada = self._cria_movimentacao(dias_atraso=8)
        mov_atrasada.status = constants.ACEITA
        mov_atrasada.save(update_fields=["status"])

        request = self.factory.get("/admin", {"atrasada": "1"})
        filtro = MovimentacaoAtrasadaFilter(
            request, {"atrasada": "1"}, MovimentacaoBemPatrimonial, self.model_admin
        )
        qs = filtro.queryset(request, MovimentacaoBemPatrimonial.objects.all())

        self.assertNotIn(mov_atrasada, qs)

    def test_filter_sem_parametro(self):
        self._cria_movimentacao(dias_atraso=8)
        request = self.factory.get("/admin")
        filtro = MovimentacaoAtrasadaFilter(
            request, {}, MovimentacaoBemPatrimonial, self.model_admin
        )
        qs = filtro.queryset(request, MovimentacaoBemPatrimonial.objects.all())
        self.assertEqual(qs.count(), 1)
