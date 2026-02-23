"""Testes para bem_patrimonial.admins.filters.movimentacao_filters."""
from datetime import timedelta

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase
from django.utils import timezone

from bem_patrimonial.admins.filters.movimentacao_filters import MovimentacaoAtrasadaFilter
from bem_patrimonial import constants
from bem_patrimonial.models import MovimentacaoBemPatrimonial
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario


class TestMovimentacaoAtrasadaFilter(TestCase):
    """Testes para MovimentacaoAtrasadaFilter."""

    def setUp(self):
        self.factory = RequestFactory()
        self.uo = criar_uo(codigo="601")
        self.ua_origem = criar_ua(uo=self.uo, codigo="601", nome="UA O")
        self.ua_destino = criar_ua(uo=self.uo, codigo="602", nome="UA D")
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        self.site = AdminSite()
        self.changelist = None

    def test_title_e_parameter_name(self):
        """Filter tem title e parameter_name corretos."""
        self.assertEqual(MovimentacaoAtrasadaFilter.title, "Movimentação atrasada")
        self.assertEqual(MovimentacaoAtrasadaFilter.parameter_name, "atrasada")

    def test_lookups(self):
        """lookups retorna Sim e Não."""
        request = self.factory.get("/")
        filtro = MovimentacaoAtrasadaFilter(
            request, {}, MovimentacaoBemPatrimonial, type("Admin", (), {})()
        )
        lookups = list(filtro.lookups(request, None))
        self.assertEqual(lookups, [("1", "Sim"), ("0", "Não")])

    def test_choices_gera_dois_itens(self):
        """choices gera opção Não e Sim."""
        request = self.factory.get("/")
        changelist = MagicMockChangelist()
        filtro = MovimentacaoAtrasadaFilter(
            request, {}, MovimentacaoBemPatrimonial, type("Admin", (), {})()
        )
        choices = list(filtro.choices(changelist))
        self.assertEqual(len(choices), 2)
        displays = [c["display"] for c in choices]
        self.assertIn("Não", displays)
        self.assertIn("Sim", displays)

    def test_queryset_atrasada_1_filtra_enviada_e_antiga(self):
        """Com atrasada=1 retorna só movimentações ENVIADA e criado_em há mais de 7 dias."""
        mov_antiga = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.user,
            status=constants.ENVIADA,
        )
        MovimentacaoBemPatrimonial.objects.filter(pk=mov_antiga.pk).update(
            criado_em=timezone.now() - timedelta(days=8)
        )
        mov_recente = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.user,
            status=constants.ENVIADA,
        )
        MovimentacaoBemPatrimonial.objects.filter(pk=mov_recente.pk).update(
            criado_em=timezone.now() - timedelta(days=2)
        )

        request = self.factory.get("/", {"atrasada": "1"})
        filtro = MovimentacaoAtrasadaFilter(
            request, {"atrasada": "1"}, MovimentacaoBemPatrimonial, None
        )
        qs = filtro.queryset(request, MovimentacaoBemPatrimonial.objects.all())
        self.assertIn(mov_antiga, qs)
        self.assertNotIn(mov_recente, qs)

    def test_queryset_sem_valor_retorna_queryset_intacto(self):
        """Sem parâmetro atrasada retorna o queryset sem filtrar."""
        mov = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.user,
            status=constants.ENVIADA,
        )
        request = self.factory.get("/")
        filtro = MovimentacaoAtrasadaFilter(request, {}, MovimentacaoBemPatrimonial, None)
        qs = filtro.queryset(request, MovimentacaoBemPatrimonial.objects.all())
        self.assertIn(mov, qs)


class MagicMockChangelist:
    def get_query_string(self, new_params=None):
        if new_params:
            return "?" + "&".join(f"{k}={v}" for k, v in new_params.items())
        return "?"
