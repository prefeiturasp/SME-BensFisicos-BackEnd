"""Testes para inventario.conciliacao (registrar_ocorrencia, excluir_ocorrencia, finalizar_conciliacao)."""
import datetime
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants as bem_constants
from dados_comuns.tests.factories import criar_ua
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO

from inventario import constants
from inventario.models import ConciliacaoUA, ItemConciliacao
from inventario.conciliacao import (
    registrar_ocorrencia,
    excluir_ocorrencia,
    finalizar_conciliacao,
)
from inventario.utils_conciliacao.conciliacao_utils import criar_itens_conciliacao


class TestRegistrarOcorrenciaValidacoes(TestCase):
    """Testes de validação de registrar_ocorrencia (BAIXA_FISICA, conciliação fechada)."""

    def setUp(self):
        self.ua = criar_ua(codigo="001.0001", sigla="UA", nome="Unidade")
        self.grupo, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.ua.unidade_orcamentaria,
        )
        self.user.groups.add(self.grupo)
        self.bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000001-0",
            nome="Bem",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.user,
        )
        self.conciliacao = ConciliacaoUA.objects.create(
            numero_conciliacao="001.0001/2025",
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=datetime.date(2025, 6, 30),
            unidade_administrativa=self.ua,
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.user,
        )
        criar_itens_conciliacao(self.conciliacao)
        self.item = ItemConciliacao.objects.get(
            conciliacao=self.conciliacao, bem=self.bem
        )

    def test_baixa_fisica_nao_pode_ser_registrada_manualmente(self):
        """registrar_ocorrencia com situacao BAIXA_FISICA levanta ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            registrar_ocorrencia(
                item=self.item,
                situacao=constants.BAIXA_FISICA,
                usuario=self.user,
            )
        self.assertIn("Baixa Física", str(ctx.exception))
        self.assertIn("não pode ser registrada", str(ctx.exception))

    def test_conciliacao_fechada_nao_permite_registrar(self):
        """registrar_ocorrencia em conciliação fechada levanta ValidationError."""
        self.conciliacao.finalizar(self.user)
        self.conciliacao.refresh_from_db()
        self.item.refresh_from_db()
        with self.assertRaises(ValidationError) as ctx:
            registrar_ocorrencia(
                item=self.item,
                situacao=constants.NAO_ENCONTRADO,
                observacao="Teste",
                usuario=self.user,
            )
        self.assertIn("fechado", str(ctx.exception))


class TestExcluirOcorrenciaValidacao(TestCase):
    """Testes de validação de excluir_ocorrencia."""

    def setUp(self):
        self.ua = criar_ua(codigo="001.0002", sigla="UA2", nome="Unidade 2")
        self.grupo, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.user = Usuario.objects.create_user(
            username="user2",
            password="x",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.ua.unidade_orcamentaria,
        )
        self.user.groups.add(self.grupo)
        self.bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000002-0",
            nome="Bem 2",
            valor_unitario=100,
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.user,
        )
        self.conciliacao = ConciliacaoUA.objects.create(
            numero_conciliacao="001.0002/2025",
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=datetime.date(2025, 6, 30),
            unidade_administrativa=self.ua,
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.user,
        )
        criar_itens_conciliacao(self.conciliacao)
        self.item = ItemConciliacao.objects.get(
            conciliacao=self.conciliacao, bem=self.bem
        )

    def test_excluir_sem_ocorrencia_levanta_erro(self):
        """excluir_ocorrencia em item sem ocorrência levanta ValidationError."""
        with self.assertRaises(ValidationError) as ctx:
            excluir_ocorrencia(item=self.item, usuario=self.user)
        self.assertIn("não tem ocorrência", str(ctx.exception))

    def test_conciliacao_fechada_nao_permite_excluir(self):
        """excluir_ocorrencia em conciliação fechada levanta ValidationError."""
        registrar_ocorrencia(
            item=self.item,
            situacao=constants.NAO_ENCONTRADO,
            observacao="Obs",
            usuario=self.user,
        )
        self.conciliacao.finalizar(self.user)
        self.item.refresh_from_db()
        with self.assertRaises(ValidationError) as ctx:
            excluir_ocorrencia(item=self.item, usuario=self.user)
        self.assertIn("fechado", str(ctx.exception))


class TestFinalizarConciliacao(TestCase):
    """Testes para finalizar_conciliacao."""

    def setUp(self):
        self.ua = criar_ua(codigo="001.0003", sigla="UA3", nome="Unidade 3")
        self.user = Usuario.objects.create_user(
            username="user3",
            password="x",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.ua.unidade_orcamentaria,
        )
        self.conciliacao = ConciliacaoUA.objects.create(
            numero_conciliacao="001.0003/2025",
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=datetime.date(2025, 6, 30),
            unidade_administrativa=self.ua,
            status=constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.user,
        )

    def test_finalizar_conciliacao_altera_status(self):
        """finalizar_conciliacao chama conciliacao.finalizar e altera status."""
        self.assertEqual(self.conciliacao.status, constants.CONCILIACAO_EM_ABERTO)
        finalizar_conciliacao(self.conciliacao, self.user)
        self.conciliacao.refresh_from_db()
        self.assertEqual(self.conciliacao.status, constants.CONCILIACAO_FECHADO)
        self.assertEqual(self.conciliacao.fechado_por_id, self.user.pk)
