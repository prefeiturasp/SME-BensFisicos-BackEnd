"""Testes para bem_patrimonial.admins.inlines.inlines."""
from django.core.exceptions import ValidationError
from django.forms.models import inlineformset_factory
from django.test import TestCase

from bem_patrimonial.models import MovimentacaoBemPatrimonial, MovimentacaoBensItem, BemPatrimonial
from bem_patrimonial.admins.inlines.inlines import (
    MovimentacaoBensItemInlineFormSet,
    MovimentacaoBensItemInlineForm,
    MovimentacaoBensItemInline,
)
from bem_patrimonial import constants
from dados_comuns.tests.factories import criar_ua, criar_uo
from inventario.models import ConciliacaoUA, ItemConciliacao
from inventario import constants as inv_constants
from usuario.models import Usuario
from django.utils import timezone


class TestMovimentacaoBensItemInlineFormSet(TestCase):
    """Testes para MovimentacaoBensItemInlineFormSet."""

    def setUp(self):
        self.uo = criar_uo()
        self.ua_origem = criar_ua(uo=self.uo, status="ativa")
        self.ua_destino = criar_ua(uo=self.uo, status="ativa")
        self.usuario = Usuario.objects.create_user(
            username="user",
            password="x",
            email="user@test.com",
            unidade_administrativa=self.ua_origem,
            unidade_orcamentaria=self.uo,
        )
        self.movimentacao = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.usuario,
        )

    def _mk_bem(self, **kwargs):
        defaults = {
            "nome": "Bem Teste",
            "descricao": "Desc",
            "valor_unitario": 100,
            "marca": "M",
            "modelo": "X",
            "numero_processo": "PROC-1",
            "unidade_administrativa": self.ua_origem,
            "criado_por": self.usuario,
            "status": constants.APROVADO,
            "sem_numeracao": True,
            "numero_patrimonial": None,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def _mk_formset(self, data=None, instance=None):
        FormSet = inlineformset_factory(
            MovimentacaoBemPatrimonial,
            MovimentacaoBensItem,
            formset=MovimentacaoBensItemInlineFormSet,
            fields=("bem",),
            extra=1,
        )
        return FormSet(data or {}, instance=instance or self.movimentacao, prefix="itens")

    def test_init_desabilita_delete(self):
        """Init desabilita campo DELETE."""
        formset = self._mk_formset()
        for form in formset.forms:
            if "DELETE" in form.fields:
                self.assertTrue(form.fields["DELETE"].disabled)

    def test_clean_sem_bens_levanta_erro(self):
        """Clean sem bens levanta ValidationError."""
        formset = self._mk_formset({
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
        })
        # O erro é levantado no clean, não no is_valid diretamente
        formset.is_valid()  # Chama is_valid que chama clean
        self.assertFalse(formset.is_valid())
        self.assertIn("ao menos um bem", str(formset.non_form_errors()).lower())

    def test_clean_com_bem_aguardando_aprovacao_levanta_erro(self):
        """Clean com bem aguardando aprovação levanta erro."""
        bem = self._mk_bem(status=constants.AGUARDANDO_APROVACAO)
        formset = self._mk_formset({
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-bem": bem.pk,
        })
        formset.is_valid()  # Chama is_valid que chama clean
        self.assertFalse(formset.is_valid())
        self.assertIn("aguardando aprovação", str(formset.non_form_errors()).lower())

    def test_clean_com_bem_bloqueado_levanta_erro(self):
        """Clean com bem bloqueado levanta erro."""
        bem = self._mk_bem(status=constants.BLOQUEADO)
        formset = self._mk_formset({
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-bem": bem.pk,
        })
        formset.is_valid()  # Chama is_valid que chama clean
        self.assertFalse(formset.is_valid())
        self.assertIn("bloqueado", str(formset.non_form_errors()).lower())

    def test_clean_com_bem_bloqueado_conciliacao_levanta_erro(self):
        """Clean com bem bloqueado por conciliação levanta erro."""
        bem = self._mk_bem()
        # Criar conciliação eventual com periodo_final
        conciliacao = ConciliacaoUA.objects.create(
            unidade_administrativa=self.ua_origem,
            tipo=inv_constants.CONCILIACAO_EVENTUAL,
            periodo_final=timezone.localdate(),
            status=inv_constants.CONCILIACAO_EM_ABERTO,
            criado_por=self.usuario,
        )
        item = ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=inv_constants.EM_PROCESSO_BAIXA_FISICA,
        )
        # bloqueado_conciliacao é um campo booleano no modelo
        bem.bloqueado_conciliacao = True
        bem.save()
        
        formset = self._mk_formset({
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-bem": bem.pk,
        })
        formset.is_valid()  # Chama is_valid que chama clean
        self.assertFalse(formset.is_valid())
        self.assertIn("bloqueado", str(formset.non_form_errors()).lower())
        self.assertIn("inventário", str(formset.non_form_errors()).lower())

    def test_clean_com_bem_nao_aprovado_levanta_erro(self):
        """Clean com bem não aprovado levanta erro."""
        bem = self._mk_bem(status=constants.NAO_APROVADO)
        formset = self._mk_formset({
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-bem": bem.pk,
        })
        formset.is_valid()  # Chama is_valid que chama clean
        self.assertFalse(formset.is_valid())
        self.assertIn("aprovados", str(formset.non_form_errors()).lower())

    def test_clean_com_bem_com_movimentacao_pendente_levanta_erro(self):
        """Clean com bem com movimentação pendente levanta erro."""
        bem = self._mk_bem()
        # Criar movimentação pendente (status ENVIADA)
        mov_pendente = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.usuario,
            status=constants.ENVIADA,
        )
        MovimentacaoBensItem.objects.create(
            movimentacao=mov_pendente,
            bem=bem,
        )
        # tem_movimentacao_pendente é uma propriedade que verifica movimentações ENVIADA
        # Já criamos uma movimentação ENVIADA acima, então a propriedade deve retornar True
        
        formset = self._mk_formset({
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-bem": bem.pk,
        })
        formset.is_valid()  # Chama is_valid que chama clean
        self.assertFalse(formset.is_valid())
        self.assertIn("movimentação pendente", str(formset.non_form_errors()).lower())

    def test_clean_com_bem_aprovado_valido(self):
        """Clean com bem aprovado é válido."""
        bem = self._mk_bem(status=constants.APROVADO)
        formset = self._mk_formset({
            "itens-TOTAL_FORMS": "1",
            "itens-INITIAL_FORMS": "0",
            "itens-MIN_NUM_FORMS": "0",
            "itens-MAX_NUM_FORMS": "1000",
            "itens-0-bem": bem.pk,
        })
        self.assertTrue(formset.is_valid())

class TestMovimentacaoBensItemInlineForm(TestCase):
    """Testes para MovimentacaoBensItemInlineForm."""

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

    def _mk_bem(self, **kwargs):
        defaults = {
            "nome": "Bem Teste",
            "descricao": "Desc",
            "valor_unitario": 100,
            "marca": "Marca",
            "modelo": "Modelo",
            "numero_processo": "PROC-1",
            "unidade_administrativa": self.ua,
            "criado_por": self.usuario,
            "status": constants.APROVADO,
            "sem_numeracao": True,
            "numero_patrimonial": None,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)

    def test_label_from_instance(self):
        """label_from_instance formata corretamente."""
        bem = self._mk_bem(numero_patrimonial="000.000000001-0", sem_numeracao=False)
        form = MovimentacaoBensItemInlineForm()
        label = form.fields["bem"].label_from_instance(bem)
        self.assertIn("000.000000001-0", label)
        self.assertIn("Bem Teste", label)
        self.assertIn("Marca", label)
        self.assertIn("Modelo", label)

    def test_label_from_instance_sem_numero(self):
        """label_from_instance funciona com bem sem número."""
        bem = self._mk_bem()
        form = MovimentacaoBensItemInlineForm()
        label = form.fields["bem"].label_from_instance(bem)
        self.assertIn("SEM-NUMERO", label)
        self.assertIn("Bem Teste", label)


class TestMovimentacaoBensItemInline(TestCase):
    """Testes para MovimentacaoBensItemInline."""

    def setUp(self):
        from django.contrib.admin.sites import AdminSite
        self.site = AdminSite()

    def test_has_add_permission_apenas_sem_obj(self):
        """has_add_permission retorna True apenas quando obj é None."""
        inline = MovimentacaoBensItemInline(MovimentacaoBemPatrimonial, self.site)
        request = type("Request", (), {"user": None})()
        
        self.assertTrue(inline.has_add_permission(request, None))
        obj = type("Obj", (), {"pk": 1})()
        self.assertFalse(inline.has_add_permission(request, obj))
