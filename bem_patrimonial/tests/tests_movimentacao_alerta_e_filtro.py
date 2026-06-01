from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua
from datetime import timedelta

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from bem_patrimonial.admins.filters.movimentacao_filters import (
    MovimentacaoAtrasadaFilter,
    IntervaloNpDeFilter,
    IntervaloNpAteFilter,
)
from bem_patrimonial import constants
from bem_patrimonial.models import (
    MovimentacaoBemPatrimonial,
    MovimentacaoBensItem,
    BemPatrimonial,
)
from bem_patrimonial.templatetags.movimentacoes_pendentes_tags import (
    alerta_movimentacoes_pendentes,
)
from dados_comuns.tests.factories import criar_ua
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario


class AlertaMovimentacoesPendentesTagTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.ua_origem = criar_ua(
            nome="UA Origem", codigo=codigo_ua(0, 0, 0, 100), sigla="UA-O"
        )
        self.ua_destino = criar_ua(
            uo=self.ua_origem.unidade_orcamentaria,
            nome="UA Destino",
            codigo=codigo_ua(0, 0, 0, 200),
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
        self.ua_origem = criar_ua(
            nome="UA Origem", codigo=codigo_ua(0, 0, 0, 101), sigla="UA-O"
        )
        self.ua_destino = criar_ua(
            uo=self.ua_origem.unidade_orcamentaria,
            nome="UA Destino",
            codigo=codigo_ua(0, 0, 0, 201),
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


# ---------------------------------------------------------------------------
# Helpers compartilhados pelos testes do filtro de intervalo
# ---------------------------------------------------------------------------

class IntervaloFilterBaseTestCase(TestCase):
    """
    Base com setUp completo: duas UAs, um usuário, duas movimentações
    com bens de números patrimoniais distintos.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.ua_origem = criar_ua(
            nome="UA Origem", codigo=codigo_ua(0, 0, 0, 102), sigla="UA-O"
        )
        self.ua_destino = criar_ua(
            uo=self.ua_origem.unidade_orcamentaria,
            nome="UA Destino",
            codigo=codigo_ua(0, 0, 0, 202),
            sigla="UA-D",
        )
        self.usuario = Usuario.objects.create_user(
            username="operador3",
            **auth_kwargs("test123"),
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.ua_origem.unidade_orcamentaria,
        )
        self.model_admin = admin.ModelAdmin(MovimentacaoBemPatrimonial, AdminSite())

        # Bem com número baixo — vinculado à movimentação A
        self.bem_baixo = BemPatrimonial.objects.create(
            nome="Bem Baixo",
            numero_patrimonial="003.000000034-8",
            unidade_administrativa=self.ua_origem,
            status=constants.APROVADO,
            valor_unitario="1.00",
        )
        # Bem com número alto — vinculado à movimentação B
        self.bem_alto = BemPatrimonial.objects.create(
            nome="Bem Alto",
            numero_patrimonial="480.299999996-9",
            unidade_administrativa=self.ua_origem,
            status=constants.APROVADO,
            valor_unitario="1.00",
        )

        self.mov_a = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.usuario,
            status=constants.ENVIADA,
        )
        MovimentacaoBensItem.objects.create(movimentacao=self.mov_a, bem=self.bem_baixo)

        self.mov_b = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.usuario,
            status=constants.ENVIADA,
        )
        MovimentacaoBensItem.objects.create(movimentacao=self.mov_b, bem=self.bem_alto)

    def _filtro_de(self, np_de="", np_ate=""):
        params = {}
        if np_de:
            params["np_de"] = np_de
        if np_ate:
            params["np_ate"] = np_ate
        request = self.factory.get("/admin", params)
        return IntervaloNpDeFilter(
            request, params, MovimentacaoBemPatrimonial, self.model_admin
        ), request

    def _qs(self):
        return MovimentacaoBemPatrimonial.objects.all()


# ---------------------------------------------------------------------------
# Testes de IntervaloNpDeFilter
# ---------------------------------------------------------------------------

class IntervaloNpDeFiltroQuerysetTestCase(IntervaloFilterBaseTestCase):

    def test_sem_parametros_retorna_tudo(self):
        filtro, request = self._filtro_de()
        qs = filtro.queryset(request, self._qs())
        self.assertIn(self.mov_a, qs)
        self.assertIn(self.mov_b, qs)

    def test_apenas_np_de_exclui_abaixo(self):
        # De: 100... → exclui 003..., mantém 480...
        filtro, request = self._filtro_de(np_de="100.000000000-0")
        qs = filtro.queryset(request, self._qs())
        self.assertNotIn(self.mov_a, qs)
        self.assertIn(self.mov_b, qs)

    def test_apenas_np_ate_exclui_acima(self):
        # Até: 200... → mantém 003..., exclui 480...
        filtro, request = self._filtro_de(np_ate="200.000000000-0")
        qs = filtro.queryset(request, self._qs())
        self.assertIn(self.mov_a, qs)
        self.assertNotIn(self.mov_b, qs)

    def test_range_pega_apenas_mov_a(self):
        # De: 003... Até: 003... → só mov_a
        filtro, request = self._filtro_de(
            np_de="003.000000034-8",
            np_ate="003.000000034-8",
        )
        qs = filtro.queryset(request, self._qs())
        self.assertIn(self.mov_a, qs)
        self.assertNotIn(self.mov_b, qs)

    def test_range_pega_apenas_mov_b(self):
        # De: 480... Até: 480... → só mov_b
        filtro, request = self._filtro_de(
            np_de="480.299999996-9",
            np_ate="480.299999996-9",
        )
        qs = filtro.queryset(request, self._qs())
        self.assertNotIn(self.mov_a, qs)
        self.assertIn(self.mov_b, qs)

    def test_range_nao_pega_nenhuma(self):
        # De: 100... Até: 200... — nenhum bem cai nesse intervalo
        filtro, request = self._filtro_de(
            np_de="100.000000000-0",
            np_ate="200.000000000-0",
        )
        qs = filtro.queryset(request, self._qs())
        self.assertNotIn(self.mov_a, qs)
        self.assertNotIn(self.mov_b, qs)

    def test_range_pega_ambas(self):
        # De: 001... Até: 999... → ambas
        filtro, request = self._filtro_de(
            np_de="001.000000000-0",
            np_ate="999.000000000-0",
        )
        qs = filtro.queryset(request, self._qs())
        self.assertIn(self.mov_a, qs)
        self.assertIn(self.mov_b, qs)

    def test_distinct_sem_duplicatas(self):
        # Movimentação com dois bens no intervalo não deve aparecer duplicada
        bem_extra = BemPatrimonial.objects.create(
            nome="Bem Extra",
            numero_patrimonial="003.000000035-9",
            unidade_administrativa=self.ua_origem,
            status=constants.APROVADO,
            valor_unitario="1.00",
        )
        MovimentacaoBensItem.objects.create(movimentacao=self.mov_a, bem=bem_extra)

        filtro, request = self._filtro_de(
            np_de="003.000000034-8",
            np_ate="003.000000035-9",
        )
        qs = filtro.queryset(request, self._qs())
        # mov_a tem dois bens no intervalo — sem distinct apareceria duas vezes
        self.assertEqual(qs.filter(pk=self.mov_a.pk).count(), 1)

    def test_np_de_com_espacos_em_branco_e_ignorado(self):
        # Valor vazio (só espaços) deve ser tratado como ausente
        filtro, request = self._filtro_de(np_de="   ", np_ate="   ")
        qs = filtro.queryset(request, self._qs())
        self.assertIn(self.mov_a, qs)
        self.assertIn(self.mov_b, qs)


class IntervaloNpDeFiltroMetadataTestCase(IntervaloFilterBaseTestCase):

    def test_has_output_retorna_true(self):
        filtro, _ = self._filtro_de()
        self.assertTrue(filtro.has_output())

    def test_lookups_retorna_vazio(self):
        filtro, request = self._filtro_de()
        self.assertEqual(list(filtro.lookups(request, self.model_admin)), [])

    def test_choices_retorna_um_item(self):
        filtro, _ = self._filtro_de()
        # choices() é um generator — precisa de changelist mock mínimo

        class FakeChangelist:
            params = {}

            def get_query_string(self, *a, **kw):
                return ""
        choices = list(filtro.choices(FakeChangelist()))
        self.assertEqual(len(choices), 1)

    def test_title(self):
        filtro, _ = self._filtro_de()
        self.assertEqual(filtro.title, "Por Intervalo")

    def test_parameter_name(self):
        filtro, _ = self._filtro_de()
        self.assertEqual(filtro.parameter_name, "np_de")

    def test_template(self):
        filtro, _ = self._filtro_de()
        self.assertEqual(
            filtro.template,
            "admin/bem_patrimonial/filters/intervalo_numero_patrimonial.html",
        )


# ---------------------------------------------------------------------------
# Testes de IntervaloNpAteFilter (filtro fantasma)
# ---------------------------------------------------------------------------

class IntervaloNpAteFiltroTestCase(IntervaloFilterBaseTestCase):

    def _filtro_ate(self, np_ate=""):
        params = {"np_ate": np_ate} if np_ate else {}
        request = self.factory.get("/admin", params)
        return IntervaloNpAteFilter(
            request, params, MovimentacaoBemPatrimonial, self.model_admin
        ), request

    def test_has_output_retorna_false(self):
        filtro, _ = self._filtro_ate()
        self.assertFalse(filtro.has_output())

    def test_queryset_nao_filtra(self):
        # O filtro fantasma nunca altera o queryset
        filtro, request = self._filtro_ate(np_ate="003.000000034-8")
        qs_original = self._qs()
        qs_filtrado = filtro.queryset(request, qs_original)
        self.assertEqual(
            list(qs_original.order_by("pk")),
            list(qs_filtrado.order_by("pk")),
        )

    def test_lookups_retorna_vazio(self):
        filtro, request = self._filtro_ate()
        self.assertEqual(list(filtro.lookups(request, self.model_admin)), [])

    def test_parameter_name(self):
        filtro, _ = self._filtro_ate()
        self.assertEqual(filtro.parameter_name, "np_ate")

    def test_template_vazio(self):
        filtro, _ = self._filtro_ate()
        self.assertEqual(
            filtro.template,
            "admin/bem_patrimonial/filters/filtro_vazio.html",
        )
