"""Testes para bem_patrimonial.models (BemPatrimonial, StatusBemPatrimonial, MovimentacaoBemPatrimonial, etc.)."""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase

from bem_patrimonial.models import (
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
    MovimentacaoBensItem,
    StatusBemPatrimonial,
)
from bem_patrimonial import constants
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario


class TestBemPatrimonialStr(TestCase):
    def setUp(self):
        self.uo = criar_uo(codigo="701")
        self.ua = criar_ua(uo=self.uo, codigo="701", nome="UA")
        self.user = Usuario.objects.create_user(
            username="user", password="x", unidade_orcamentaria=self.uo
        )

    def test_str_com_numero_patrimonial(self):
        bem = BemPatrimonial(
            nome="Bem",
            descricao="Desc",
            valor_unitario=Decimal("100"),
            marca="M",
            modelo="X",
            numero_patrimonial="001.000000001-0",
            status=constants.APROVADO,
        )
        self.assertIn("001.000000001-0", str(bem))
        self.assertIn("Bem", str(bem))

    def test_str_sem_numero_retorna_nome(self):
        bem = BemPatrimonial(
            nome="Só Nome",
            descricao="Desc",
            valor_unitario=Decimal("100"),
            marca="M",
            modelo="X",
            numero_patrimonial=None,
            status=constants.APROVADO,
        )
        self.assertEqual(str(bem), "Só Nome")


class TestBemPatrimonialClean(TestCase):
    def setUp(self):
        self.uo = criar_uo(codigo="702")
        self.ua = criar_ua(uo=self.uo, codigo="702", nome="UA")
        self.user = Usuario.objects.create_user(
            username="user", password="x", unidade_orcamentaria=self.uo
        )

    def test_formato_antigo_e_sem_numeracao_ambos_levanta_erro(self):
        bem = BemPatrimonial(
            nome="Bem",
            descricao="Desc",
            valor_unitario=Decimal("100"),
            marca="M",
            modelo="X",
            numero_formato_antigo=True,
            sem_numeracao=True,
            status=constants.APROVADO,
        )
        with self.assertRaises(ValidationError) as ctx:
            bem.clean()
        self.assertIn("Formato antigo", str(ctx.exception))
        self.assertIn("Sem numeração", str(ctx.exception))

    def test_sem_numero_e_sem_sem_numeracao_levanta_erro(self):
        bem = BemPatrimonial(
            nome="Bem",
            descricao="Desc",
            valor_unitario=Decimal("100"),
            marca="M",
            modelo="X",
            numero_patrimonial="",
            sem_numeracao=False,
            status=constants.APROVADO,
        )
        with self.assertRaises(ValidationError) as ctx:
            bem.clean()
        self.assertIn("numero_patrimonial", ctx.exception.message_dict)

    def test_numero_incompleto_levanta_erro(self):
        bem = BemPatrimonial(
            nome="Bem",
            descricao="Desc",
            valor_unitario=Decimal("100"),
            marca="M",
            modelo="X",
            numero_patrimonial="001.123",
            numero_formato_antigo=False,
            sem_numeracao=False,
            status=constants.APROVADO,
        )
        with self.assertRaises(ValidationError) as ctx:
            bem.clean()
        self.assertIn("numero_patrimonial", ctx.exception.message_dict)


class TestBemPatrimonialProperties(TestCase):
    def setUp(self):
        self.uo = criar_uo(codigo="703")
        self.ua = criar_ua(uo=self.uo, codigo="703", nome="UA")
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.bem = BemPatrimonial.objects.create(
            nome="Bem",
            descricao="Desc",
            valor_unitario=Decimal("100"),
            marca="M",
            modelo="X",
            numero_patrimonial="001.000000003-0",
            unidade_administrativa=self.ua,
            criado_por=self.user,
            status=constants.APROVADO,
        )

    def test_pode_solicitar_movimentacao_aprovado_sem_bloqueio(self):
        self.assertTrue(self.bem.pode_solicitar_movimentacao)

    def test_pode_solicitar_movimentacao_false_se_bloqueado(self):
        self.bem.bloqueado_conciliacao = True
        self.bem.save(update_fields=["bloqueado_conciliacao"])
        self.bem.refresh_from_db()
        self.assertFalse(self.bem.pode_solicitar_movimentacao)

    def test_pode_solicitar_movimentacao_false_se_nao_aprovado(self):
        self.bem.status = constants.AGUARDANDO_APROVACAO
        self.bem.save(update_fields=["status"])
        self.bem.refresh_from_db()
        self.assertFalse(self.bem.pode_solicitar_movimentacao)

    def test_tem_movimentacao_pendente_false_sem_movimentacao(self):
        self.assertFalse(self.bem.tem_movimentacao_pendente)


class TestBemPatrimonialSaveSemNumeracao(TestCase):
    """Testes para save() com sem_numeracao atribuindo número automático."""

    def setUp(self):
        self.uo = criar_uo(codigo="704")
        self.ua = criar_ua(uo=self.uo, codigo="704", nome="UA")
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )

    def test_save_sem_numeracao_atribui_sem_numero_id(self):
        bem = BemPatrimonial.objects.create(
            nome="Bem",
            descricao="Desc",
            valor_unitario=Decimal("100"),
            marca="M",
            modelo="X",
            sem_numeracao=True,
            numero_patrimonial=None,
            unidade_administrativa=self.ua,
            criado_por=self.user,
            status=constants.APROVADO,
        )
        self.assertTrue(bem.numero_patrimonial.startswith("SEM-NUMERO-"))
        self.assertIn(str(bem.pk), bem.numero_patrimonial)


class TestSoftDeleteQuerySet(TestCase):
    """Testes para SoftDeleteQuerySet (delete, alive, dead)."""

    def setUp(self):
        self.uo = criar_uo(codigo="705")
        self.ua = criar_ua(uo=self.uo, codigo="705", nome="UA")
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.bem = BemPatrimonial.objects.create(
            nome="Bem",
            descricao="Desc",
            valor_unitario=Decimal("100"),
            marca="M",
            modelo="X",
            numero_patrimonial="001.000000005-0",
            unidade_administrativa=self.ua,
            criado_por=self.user,
            status=constants.APROVADO,
        )

    def test_queryset_delete_soft(self):
        qs = BemPatrimonial.all_objects.filter(pk=self.bem.pk)
        count_before = qs.count()
        qs.delete()
        self.bem.refresh_from_db()
        self.assertTrue(self.bem.excluido)
        self.assertEqual(BemPatrimonial.objects.filter(pk=self.bem.pk).count(), 0)
        self.assertEqual(BemPatrimonial.all_objects.filter(pk=self.bem.pk).count(), 1)

    def test_alive_exclui_excluidos(self):
        self.bem.excluido = True
        self.bem.save(update_fields=["excluido"])
        self.assertNotIn(self.bem, BemPatrimonial.objects.all())
        self.assertNotIn(self.bem, BemPatrimonial.all_objects.alive())
        self.assertIn(self.bem, BemPatrimonial.all_objects.dead())


class TestStatusBemPatrimonial(TestCase):
    def setUp(self):
        self.uo = criar_uo(codigo="706")
        self.ua = criar_ua(uo=self.uo, codigo="706", nome="UA")
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.bem = BemPatrimonial.objects.create(
            nome="Bem",
            descricao="Desc",
            valor_unitario=Decimal("100"),
            marca="M",
            modelo="X",
            numero_patrimonial="001.000000006-0",
            unidade_administrativa=self.ua,
            criado_por=self.user,
            status=constants.AGUARDANDO_APROVACAO,
        )

    def test_str_retorna_pk(self):
        status = StatusBemPatrimonial.objects.filter(bem_patrimonial=self.bem).first()
        self.assertIsNotNone(status)
        self.assertEqual(str(status), str(status.pk))


class TestMovimentacaoBensItemStr(TestCase):
    def setUp(self):
        self.uo = criar_uo(codigo="707")
        self.ua_origem = criar_ua(uo=self.uo, codigo="707", nome="O")
        self.ua_destino = criar_ua(uo=self.uo, codigo="708", nome="D")
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        self.bem = BemPatrimonial.objects.create(
            nome="Bem",
            descricao="Desc",
            valor_unitario=Decimal("100"),
            marca="M",
            modelo="X",
            numero_patrimonial="001.000000007-0",
            unidade_administrativa=self.ua_origem,
            criado_por=self.user,
            status=constants.APROVADO,
        )
        self.mov = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.user,
        )
        self.item = MovimentacaoBensItem.objects.create(
            movimentacao=self.mov, bem=self.bem
        )

    def test_str_contem_mov_e_bem(self):
        s = str(self.item)
        self.assertIn(str(self.mov.pk), s)
        self.assertIn("Mov#", s)
        self.assertIn(str(self.bem), s)


class TestMovimentacaoBemPatrimonialStr(TestCase):
    def setUp(self):
        self.uo = criar_uo(codigo="709")
        self.ua_origem = criar_ua(uo=self.uo, codigo="709", nome="O")
        self.ua_destino = criar_ua(uo=self.uo, codigo="710", nome="D")
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        self.mov = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.user,
        )

    def test_str_contem_solicitacao_e_pk(self):
        s = str(self.mov)
        self.assertIn("Solicitação", s)
        self.assertIn(str(self.mov.pk), s)


class TestMovimentacaoBemPatrimonialProperties(TestCase):
    def setUp(self):
        self.uo = criar_uo(codigo="711")
        self.ua_origem = criar_ua(uo=self.uo, codigo="711", nome="O")
        self.ua_destino = criar_ua(uo=self.uo, codigo="712", nome="D")
        self.user = Usuario.objects.create_user(
            username="user",
            password="x",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        self.mov = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.user,
            status=constants.ENVIADA,
        )

    def test_aceita_true_quando_aceita(self):
        self.mov.status = constants.ACEITA
        self.mov.save(update_fields=["status"])
        self.mov.refresh_from_db()
        self.assertTrue(self.mov.aceita)
        self.assertFalse(self.mov.rejeitada)
        self.assertFalse(self.mov.cancelada)

    def test_rejeitada_true_quando_rejeitada(self):
        self.mov.status = constants.REJEITADA
        self.mov.save(update_fields=["status"])
        self.mov.refresh_from_db()
        self.assertFalse(self.mov.aceita)
        self.assertTrue(self.mov.rejeitada)
