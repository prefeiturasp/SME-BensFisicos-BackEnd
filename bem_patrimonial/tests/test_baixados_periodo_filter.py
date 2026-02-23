"""Testes para bem_patrimonial.admins.filters.baixados_periodo_filter."""
from django.test import TestCase
from django.utils import timezone
from django.contrib.admin.sites import AdminSite
from django.db.models import OuterRef, Subquery

from bem_patrimonial.models import BemPatrimonial, BaixaFisicaBensItem, BaixaFisicaBemPatrimonial
from bem_patrimonial.admins.filters.baixados_periodo_filter import BaixadosMaisDeUmPeriodoFilter
from bem_patrimonial import constants
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario


class TestBaixadosMaisDeUmPeriodoFilter(TestCase):
    """Testes para BaixadosMaisDeUmPeriodoFilter."""

    def setUp(self):
        self.uo = criar_uo()
        self.ua = criar_ua(uo=self.uo)
        self.usuario = Usuario.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.site = AdminSite()
        self.filter = BaixadosMaisDeUmPeriodoFilter(
            None, {}, BemPatrimonial, None
        )

    def _mk_bem(self, **kwargs):
        defaults = {
            "nome": "Bem Teste",
            "descricao": "Desc",
            "valor_unitario": 100,
            "marca": "M",
            "modelo": "X",
            "numero_processo": "PROC-1",
            "unidade_administrativa": self.ua,
            "criado_por": self.usuario,
            "status": constants.BAIXA_FISICA,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def test_lookups(self):
        """lookups retorna opções corretas."""
        lookups = self.filter.lookups(None, None)
        self.assertEqual(len(lookups), 2)
        self.assertIn(("1", "Sim"), lookups)
        self.assertIn(("0", "Não"), lookups)

    def test_queryset_sem_value_retorna_todos(self):
        """queryset sem value retorna todos os bens."""
        bem1 = self._mk_bem()
        bem2 = self._mk_bem()
        queryset = BemPatrimonial.objects.all()
        filtered = self.filter.queryset(None, queryset)
        self.assertEqual(filtered.count(), 2)

    def test_queryset_value_1_filtra_antigos(self):
        """queryset com value='1' filtra bens baixados antes do período."""
        ano_corrente = timezone.localdate().year
        ano_minimo = ano_corrente - 1
        
        # Criar baixas físicas
        baixa_antiga = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua,
            numero_processo_baixa="PROC-ANTIGO",
            data_baixa=timezone.localdate().replace(year=ano_minimo - 1, month=6, day=15),
            criado_por=self.usuario,
            status=constants.ACEITA,
        )
        bem_antigo = self._mk_bem(status=constants.BAIXA_FISICA)
        BaixaFisicaBensItem.objects.create(baixa=baixa_antiga, bem=bem_antigo)
        
        baixa_periodo = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua,
            numero_processo_baixa="PROC-PERIODO",
            data_baixa=timezone.localdate().replace(year=ano_minimo, month=6, day=15),
            criado_por=self.usuario,
            status=constants.ACEITA,
        )
        bem_periodo = self._mk_bem(status=constants.BAIXA_FISICA)
        BaixaFisicaBensItem.objects.create(baixa=baixa_periodo, bem=bem_periodo)
        
        # Anotar queryset com baixa_data
        baixa_data_sq = (
            BaixaFisicaBensItem.objects.filter(bem_id=OuterRef("pk"))
            .order_by("-baixa__data_baixa")
            .values("baixa__data_baixa")[:1]
        )
        queryset = BemPatrimonial.objects.all().annotate(
            baixa_data=Subquery(baixa_data_sq),
        )
        
        # Criar filtro com value='1'
        filter_instance = BaixadosMaisDeUmPeriodoFilter(
            None, {"baixados_mais_de_um_periodo": "1"}, BemPatrimonial, None
        )
        filtered = filter_instance.queryset(None, queryset)
        
        # O filtro deve retornar apenas bens com baixa_data__year < ano_minimo
        self.assertEqual(filtered.count(), 1)
        self.assertIn(bem_antigo, filtered)
        self.assertNotIn(bem_periodo, filtered)

    def test_queryset_value_0_filtra_periodo(self):
        """queryset com value='0' filtra bens baixados no período."""
        ano_corrente = timezone.localdate().year
        ano_minimo = ano_corrente - 1
        
        # Criar baixas físicas
        baixa_periodo = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua,
            numero_processo_baixa="PROC-PERIODO",
            data_baixa=timezone.localdate().replace(year=ano_minimo, month=6, day=15),
            criado_por=self.usuario,
            status=constants.ACEITA,
        )
        bem_periodo = self._mk_bem(status=constants.BAIXA_FISICA)
        BaixaFisicaBensItem.objects.create(baixa=baixa_periodo, bem=bem_periodo)
        
        baixa_antiga = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua,
            numero_processo_baixa="PROC-ANTIGO",
            data_baixa=timezone.localdate().replace(year=ano_minimo - 1, month=6, day=15),
            criado_por=self.usuario,
            status=constants.ACEITA,
        )
        bem_antigo = self._mk_bem(status=constants.BAIXA_FISICA)
        BaixaFisicaBensItem.objects.create(baixa=baixa_antiga, bem=bem_antigo)
        
        # Anotar queryset com baixa_data
        baixa_data_sq = (
            BaixaFisicaBensItem.objects.filter(bem_id=OuterRef("pk"))
            .order_by("-baixa__data_baixa")
            .values("baixa__data_baixa")[:1]
        )
        queryset = BemPatrimonial.objects.all().annotate(
            baixa_data=Subquery(baixa_data_sq),
        )
        
        # Criar filtro com value='0'
        filter_instance = BaixadosMaisDeUmPeriodoFilter(
            None, {"baixados_mais_de_um_periodo": "0"}, BemPatrimonial, None
        )
        filtered = filter_instance.queryset(None, queryset)
        
        # O filtro deve retornar apenas bens com baixa_data__year >= ano_minimo
        self.assertEqual(filtered.count(), 1)
        self.assertIn(bem_periodo, filtered)
        self.assertNotIn(bem_antigo, filtered)

    def test_queryset_value_invalido_retorna_todos(self):
        """queryset com value inválido retorna todos."""
        bem1 = self._mk_bem()
        bem2 = self._mk_bem()
        queryset = BemPatrimonial.objects.all()
        
        # Criar filtro com value inválido
        filter_instance = BaixadosMaisDeUmPeriodoFilter(
            None, {"baixados_mais_de_um_periodo": "2"}, BemPatrimonial, None
        )
        filtered = filter_instance.queryset(None, queryset)
        
        # Deve retornar todos
        self.assertEqual(filtered.count(), 2)
