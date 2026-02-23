"""Testes para bem_patrimonial.admins.actions.movimentacoe_duplicadas."""
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from dados_comuns.models import UnidadeAdministrativa
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO

from bem_patrimonial import constants
from bem_patrimonial.models import BemPatrimonial, MovimentacaoBemPatrimonial
from bem_patrimonial.admins.actions.movimentacoe_duplicadas import (
    verificar_movimentacoes_duplicadas,
)
from bem_patrimonial.admins.movimentacao_bem_patrimonial import (
    MovimentacaoBemPatrimonialAdmin,
)


User = get_user_model()


class TestVerificarMovimentacoesDuplicadas(TestCase):
    """Testes para verificar_movimentacoes_duplicadas()."""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.uo = criar_uo()
        self.ua_origem = criar_ua(uo=self.uo, status=UnidadeAdministrativa.ATIVA)
        self.ua_destino = criar_ua(uo=self.uo, status=UnidadeAdministrativa.ATIVA)
        self.ua_outra = criar_ua(uo=self.uo, status=UnidadeAdministrativa.ATIVA)

        self.grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.grupo_operador, _ = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )

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

        self.usuario_comum = User.objects.create_user(
            username="comum",
            password="x",
            email="comum@test.com",
            is_staff=True,
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )

        self.admin = MovimentacaoBemPatrimonialAdmin(
            MovimentacaoBemPatrimonial, self.site
        )

    def _mk_bem(self, **kwargs):
        defaults = {
            "nome": "Bem Teste",
            "descricao": "Descrição",
            "valor_unitario": 100,
            "marca": "Marca",
            "modelo": "Modelo",
            "numero_processo": "PROC-1",
            "unidade_administrativa": self.ua_origem,
            "criado_por": self.gestor,
            "status": constants.APROVADO,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def _mk_movimentacao(self, bem, origem, destino, **kwargs):
        defaults = {
            "bem_patrimonial": bem,
            "unidade_administrativa_origem": origem,
            "unidade_administrativa_destino": destino,
            "solicitado_por": self.gestor,
        }
        defaults.update(kwargs)
        return MovimentacaoBemPatrimonial.objects.create(**defaults)

    def _request_com_mensagens(self, user, method="get"):
        request = getattr(self.factory, method)("/")
        request.user = user
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_requer_permissao_gestor_ou_operador(self):
        """Usuário sem permissão recebe mensagem de erro."""
        bem = self._mk_bem()
        mov = self._mk_movimentacao(bem, self.ua_origem, self.ua_destino)
        request = self._request_com_mensagens(self.usuario_comum)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=mov.pk)

        response = verificar_movimentacoes_duplicadas(
            self.admin, request, queryset
        )

        self.assertIsNone(response)
        messages = list(request._messages)
        self.assertTrue(any("permissão" in str(m).lower() for m in messages))

    def test_gestor_pode_executar(self):
        """Gestor pode executar a action."""
        bem = self._mk_bem()
        mov = self._mk_movimentacao(bem, self.ua_origem, self.ua_destino)
        request = self._request_com_mensagens(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=mov.pk)

        response = verificar_movimentacoes_duplicadas(
            self.admin, request, queryset
        )

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 200)

    def test_operador_pode_executar(self):
        """Operador pode executar a action."""
        bem = self._mk_bem()
        mov = self._mk_movimentacao(bem, self.ua_origem, self.ua_destino)
        request = self._request_com_mensagens(self.operador)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=mov.pk)

        response = verificar_movimentacoes_duplicadas(
            self.admin, request, queryset
        )

        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 200)

    def test_detecta_movimentacoes_duplicadas_mesmo_bem_mesma_origem(self):
        """Detecta quando mesmo bem sai mais de uma vez da mesma origem."""
        bem1 = self._mk_bem(nome="Bem 1")
        bem2 = self._mk_bem(nome="Bem 2")

        # Bem 1 sai duas vezes da mesma origem -> duplicado
        mov1 = self._mk_movimentacao(bem1, self.ua_origem, self.ua_destino)
        mov2 = self._mk_movimentacao(bem1, self.ua_origem, self.ua_outra)

        # Bem 2 sai uma vez -> não duplicado
        mov3 = self._mk_movimentacao(bem2, self.ua_origem, self.ua_destino)

        # Bem 1 sai de outra origem -> não conta como duplicado do grupo anterior
        mov4 = self._mk_movimentacao(bem1, self.ua_outra, self.ua_destino)

        request = self._request_com_mensagens(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.all()

        response = verificar_movimentacoes_duplicadas(
            self.admin, request, queryset
        )

        self.assertEqual(response.status_code, 200)
        context = response.context_data
        grupos = context["grupos_duplicados"]
        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0]["bem_id"], bem1.pk)
        self.assertEqual(grupos[0]["origem"], self.ua_origem)
        self.assertEqual(len(grupos[0]["movimentos"]), 2)
        self.assertIn(mov1, grupos[0]["movimentos"])
        self.assertIn(mov2, grupos[0]["movimentos"])

    def test_nao_detecta_quando_apenas_uma_movimentacao(self):
        """Não marca como duplicado quando há apenas uma movimentação."""
        bem = self._mk_bem()
        mov = self._mk_movimentacao(bem, self.ua_origem, self.ua_destino)

        request = self._request_com_mensagens(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=mov.pk)

        response = verificar_movimentacoes_duplicadas(
            self.admin, request, queryset
        )

        self.assertEqual(response.status_code, 200)
        context = response.context_data
        grupos = context["grupos_duplicados"]
        self.assertEqual(len(grupos), 0)

    def test_filtra_por_ua_quando_gestor_tem_ua(self):
        """Gestor com UA vê apenas movimentações da sua UA (origem ou destino)."""
        bem1 = self._mk_bem()
        bem2 = self._mk_bem()

        # Movimentações envolvendo UA do gestor
        mov1 = self._mk_movimentacao(
            bem1, self.ua_origem, self.ua_destino
        )  # origem = UA gestor
        mov2 = self._mk_movimentacao(
            bem1, self.ua_destino, self.ua_origem
        )  # destino = UA gestor

        # Movimentação sem envolvimento da UA do gestor
        mov3 = self._mk_movimentacao(bem2, self.ua_outra, self.ua_destino)

        request = self._request_com_mensagens(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.all()

        response = verificar_movimentacoes_duplicadas(
            self.admin, request, queryset
        )

        self.assertEqual(response.status_code, 200)
        context = response.context_data
        total_analisadas = context["total_movimentacoes_analisadas"]
        # Deve analisar apenas mov1 e mov2 (envolvem UA do gestor)
        self.assertEqual(total_analisadas, 2)

    def test_ordena_movimentos_por_id(self):
        """Movimentos dentro de cada grupo são ordenados por ID."""
        bem = self._mk_bem()
        mov3 = self._mk_movimentacao(bem, self.ua_origem, self.ua_destino)
        mov1 = self._mk_movimentacao(bem, self.ua_origem, self.ua_outra)
        mov2 = self._mk_movimentacao(bem, self.ua_origem, self.ua_destino)

        request = self._request_com_mensagens(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.all()

        response = verificar_movimentacoes_duplicadas(
            self.admin, request, queryset
        )

        self.assertEqual(response.status_code, 200)
        context = response.context_data
        grupos = context["grupos_duplicados"]
        self.assertEqual(len(grupos), 1)
        movimentos = grupos[0]["movimentos"]
        # Verifica que estão ordenados por ID (crescente)
        ids = [m.id for m in movimentos]
        self.assertEqual(ids, sorted(ids))
        # Verifica que todos os movimentos estão presentes
        self.assertIn(mov1, movimentos)
        self.assertIn(mov2, movimentos)
        self.assertIn(mov3, movimentos)

    def test_ordena_grupos_por_bem_id_e_origem(self):
        """Grupos são ordenados por bem_id e origem."""
        bem2 = self._mk_bem(nome="Bem 2")
        bem1 = self._mk_bem(nome="Bem 1")

        # Criar grupos em ordem diferente
        mov_bem2 = self._mk_movimentacao(bem2, self.ua_origem, self.ua_destino)
        self._mk_movimentacao(bem2, self.ua_origem, self.ua_outra)

        mov_bem1 = self._mk_movimentacao(bem1, self.ua_origem, self.ua_destino)
        self._mk_movimentacao(bem1, self.ua_origem, self.ua_outra)

        request = self._request_com_mensagens(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.all()

        response = verificar_movimentacoes_duplicadas(
            self.admin, request, queryset
        )

        self.assertEqual(response.status_code, 200)
        context = response.context_data
        grupos = context["grupos_duplicados"]
        self.assertEqual(len(grupos), 2)
        # Verifica que estão ordenados por bem_id (crescente)
        bem_ids = [g["bem_id"] for g in grupos]
        self.assertEqual(bem_ids, sorted(bem_ids))
        # Verifica que ambos os grupos estão presentes
        self.assertIn(bem1.pk, bem_ids)
        self.assertIn(bem2.pk, bem_ids)

    def test_contexto_inclui_metadados(self):
        """Contexto inclui título, opts, totais."""
        bem = self._mk_bem()
        mov1 = self._mk_movimentacao(bem, self.ua_origem, self.ua_destino)
        mov2 = self._mk_movimentacao(bem, self.ua_origem, self.ua_outra)

        request = self._request_com_mensagens(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.all()

        response = verificar_movimentacoes_duplicadas(
            self.admin, request, queryset
        )

        self.assertEqual(response.status_code, 200)
        context = response.context_data
        self.assertEqual(
            context["title"], "(137771) Movimentações potencialmente duplicadas"
        )
        self.assertEqual(context["opts"], MovimentacaoBemPatrimonial._meta)
        self.assertEqual(context["total_movimentacoes_analisadas"], 2)
        self.assertEqual(context["total_grupos_duplicados"], 1)

    def test_retorna_template_response(self):
        """Retorna TemplateResponse com template correto."""
        bem = self._mk_bem()
        mov = self._mk_movimentacao(bem, self.ua_origem, self.ua_destino)

        request = self._request_com_mensagens(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=mov.pk)

        response = verificar_movimentacoes_duplicadas(
            self.admin, request, queryset
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.template_name, "admin/movimentacoes_duplicadas.html"
        )

    def test_multiplos_grupos_duplicados(self):
        """Detecta múltiplos grupos de duplicados independentes."""
        bem1 = self._mk_bem(nome="Bem 1")
        bem2 = self._mk_bem(nome="Bem 2")

        # Grupo 1: bem1 sai duas vezes de ua_origem (UA do gestor)
        mov1_1 = self._mk_movimentacao(bem1, self.ua_origem, self.ua_destino)
        mov1_2 = self._mk_movimentacao(bem1, self.ua_origem, self.ua_outra)

        # Grupo 2: bem2 sai duas vezes de ua_origem também (mesma origem)
        mov2_1 = self._mk_movimentacao(bem2, self.ua_origem, self.ua_destino)
        mov2_2 = self._mk_movimentacao(bem2, self.ua_origem, self.ua_outra)

        request = self._request_com_mensagens(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.all()

        response = verificar_movimentacoes_duplicadas(
            self.admin, request, queryset
        )

        self.assertEqual(response.status_code, 200)
        context = response.context_data
        grupos = context["grupos_duplicados"]
        self.assertEqual(len(grupos), 2)
        self.assertEqual(context["total_grupos_duplicados"], 2)
        # Verifica que ambos os grupos têm a mesma origem (ua_origem)
        for grupo in grupos:
            self.assertEqual(grupo["origem"], self.ua_origem)
