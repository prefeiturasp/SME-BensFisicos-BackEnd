"""Testes para inventario.models (ParametroConciliacaoAnual, ConciliacaoUA, ItemConciliacao, OcorrenciaConciliacao)."""
from datetime import date
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants as bem_constants
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario

from inventario import constants
from inventario.models import (
    ConciliacaoUA,
    ItemConciliacao,
    OcorrenciaConciliacao,
    ParametroConciliacaoAnual,
)


class ParametroConciliacaoAnualModelTest(TestCase):
    """Testes para ParametroConciliacaoAnual (__str__, clean período obrigatório, esta_vigente)."""

    def setUp(self):
        self.uo = criar_uo(codigo="701")
        self.parametro = ParametroConciliacaoAnual(
            ano_referencia=2025,
            periodo_inicial=date(2026, 1, 1),
            periodo_final=date(2026, 3, 31),
            ativo=True,
            unidade_orcamentaria=self.uo,
        )
        self.parametro.save()

    def test_str(self):
        """__str__ retorna ano e período formatado."""
        self.assertIn("2025", str(self.parametro))
        self.assertIn("01/01/2026", str(self.parametro))
        self.assertIn("31/03/2026", str(self.parametro))

    def test_clean_periodo_obrigatorio(self):
        """clean exige periodo_inicial e periodo_final."""
        p = ParametroConciliacaoAnual(
            ano_referencia=2025,
            periodo_inicial=None,
            periodo_final=date(2026, 3, 31),
            unidade_orcamentaria=self.uo,
        )
        with self.assertRaises(ValidationError) as ctx:
            p.clean()
        self.assertIn("obrigatórios", str(ctx.exception))

    def test_esta_vigente_dentro_do_periodo(self):
        """esta_vigente True quando hoje está entre periodo_inicial e periodo_final."""
        with patch.object(timezone, "localdate", return_value=date(2026, 2, 15)):
            self.assertTrue(self.parametro.esta_vigente)

    def test_esta_vigente_fora_do_periodo(self):
        """esta_vigente False quando hoje está fora do período."""
        with patch.object(timezone, "localdate", return_value=date(2026, 5, 1)):
            self.assertFalse(self.parametro.esta_vigente)


class ConciliacaoUAModelTest(TestCase):
    """Testes para ConciliacaoUA (__str__, clean, save numero_conciliacao, finalizar, esta_aberto)."""

    def setUp(self):
        self.ua = criar_ua(codigo="001.0001", sigla="UA-Teste", nome="Unidade Teste")
        self.usuario = Usuario.objects.create_user(
            username="gestor",
            password="123",
            unidade_orcamentaria=self.ua.unidade_orcamentaria,
        )
        self.bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-0",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )

    def test_str(self):
        """__str__ retorna numero_conciliacao e sigla da UA."""
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_ANUAL,
            criado_por=self.usuario,
        )
        self.assertIn(conciliacao.numero_conciliacao, str(conciliacao))
        self.assertIn(self.ua.sigla, str(conciliacao))

    def test_clean_tipo_obrigatorio(self):
        """clean exige tipo."""
        c = ConciliacaoUA(
            unidade_administrativa=self.ua,
            tipo=None,
            criado_por=self.usuario,
        )
        with self.assertRaises(ValidationError) as ctx:
            c.clean()
        self.assertIn("tipo", str(ctx.exception).lower())

    def test_clean_eventual_exige_periodo_final(self):
        """clean exige periodo_final para conciliação eventual."""
        c = ConciliacaoUA(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=None,
            criado_por=self.usuario,
        )
        with self.assertRaises(ValidationError) as ctx:
            c.clean()
        self.assertIn("periodo_final", ctx.exception.message_dict)

    def test_save_define_numero_conciliacao_anual(self):
        """save define numero_conciliacao no formato 001.CODIGO/ANO para anual."""
        ano_ref = timezone.localdate().year - 1
        conciliacao = ConciliacaoUA(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_ANUAL,
            criado_por=self.usuario,
        )
        conciliacao.save()
        self.assertTrue(conciliacao.numero_conciliacao.startswith("001."))
        self.assertIn(str(ano_ref), conciliacao.numero_conciliacao)

    def test_finalizar_altera_status_e_fechado_por(self):
        """finalizar define status FECHADO e fechado_por."""
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_ANUAL,
            criado_por=self.usuario,
        )
        self.assertEqual(conciliacao.status, constants.CONCILIACAO_EM_ABERTO)
        conciliacao.finalizar(self.usuario)
        conciliacao.refresh_from_db()
        self.assertEqual(conciliacao.status, constants.CONCILIACAO_FECHADO)
        self.assertEqual(conciliacao.fechado_por_id, self.usuario.pk)
        self.assertIsNotNone(conciliacao.fechado_em)

    def test_finalizar_ja_fechado_nao_altera(self):
        """finalizar quando já fechado não altera novamente."""
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_ANUAL,
            criado_por=self.usuario,
        )
        conciliacao.finalizar(self.usuario)
        fechado_em = conciliacao.fechado_em
        conciliacao.finalizar(self.usuario)
        conciliacao.refresh_from_db()
        self.assertEqual(conciliacao.fechado_em, fechado_em)

    def test_esta_aberto(self):
        """esta_aberto True quando status em_aberto."""
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_ANUAL,
            criado_por=self.usuario,
        )
        self.assertTrue(conciliacao.esta_aberto)
        conciliacao.finalizar(self.usuario)
        conciliacao.refresh_from_db()
        self.assertFalse(conciliacao.esta_aberto)


class ItemConciliacaoModelTest(TestCase):
    """Testes para ItemConciliacao (__str__, clean divergência)."""

    def setUp(self):
        self.ua = criar_ua(codigo="001.0001", sigla="UA", nome="Unidade Teste")
        self.usuario = Usuario.objects.create_user(
            username="gestor",
            password="123",
            unidade_orcamentaria=self.ua.unidade_orcamentaria,
        )
        self.bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000002-0",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        self.conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_ANUAL,
            criado_por=self.usuario,
        )

    def test_str(self):
        """__str__ contém numero_patrimonial e situação."""
        item = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao,
            bem=self.bem,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
        )
        self.assertIn(self.bem.numero_patrimonial, str(item))

    def test_clean_divergente_exige_divergencia(self):
        """clean exige divergencia quando situacao é Divergente."""
        item = ItemConciliacao(
            conciliacao=self.conciliacao,
            bem=self.bem,
            situacao=constants.DIVERGENTE,
            divergencia="",
        )
        with self.assertRaises(ValidationError) as ctx:
            item.clean()
        self.assertIn("divergencia", ctx.exception.message_dict)

    def test_clean_nao_divergente_nao_permite_divergencia(self):
        """clean não permite divergencia preenchida quando situação não é Divergente."""
        item = ItemConciliacao(
            conciliacao=self.conciliacao,
            bem=self.bem,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
            divergencia="Algo preenchido",
        )
        with self.assertRaises(ValidationError) as ctx:
            item.clean()
        self.assertIn("divergencia", ctx.exception.message_dict)


class OcorrenciaConciliacaoModelTest(TestCase):
    """Testes para OcorrenciaConciliacao (__str__)."""

    def setUp(self):
        self.ua = criar_ua(codigo="001.0001", sigla="UA", nome="Unidade Teste")
        self.usuario = Usuario.objects.create_user(
            username="gestor",
            password="123",
            unidade_orcamentaria=self.ua.unidade_orcamentaria,
        )
        self.bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000003-0",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )
        self.conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua,
            tipo=constants.CONCILIACAO_ANUAL,
            criado_por=self.usuario,
        )
        self.item = ItemConciliacao.objects.create(
            conciliacao=self.conciliacao,
            bem=self.bem,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
        )

    def test_str(self):
        """__str__ contém numero_patrimonial do bem e situação."""
        oc = OcorrenciaConciliacao.objects.create(
            item=self.item,
            situacao=constants.DIVERGENTE,
            registrado_por=self.usuario,
        )
        self.assertIn(self.bem.numero_patrimonial, str(oc))
