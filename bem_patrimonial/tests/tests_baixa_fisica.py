from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from unittest.mock import patch
from django.utils import timezone

from bem_patrimonial.models import (
    BemPatrimonial,
    BaixaFisicaBemPatrimonial,
    BaixaFisicaBensItem,
)
from bem_patrimonial.constants import (
    APROVADO,
    BAIXA_FISICA,
    BAIXA_FISICA_AGUARDANDO_APROVACAO,
    AGUARDANDO_ENVIO,
    ENVIADA,
    ACEITA,
    SOLICITADA,
    RECUSADA,
)
from bem_patrimonial.admins.baixa_fisica_bem_patrimonial import (
    BaixaFisicaBemPatrimonialAdmin,
    BaixaFisicaBensItemInlineFormSet,
)

# reaproveita helpers usados nos testes de movimentação
from bem_patrimonial.tests.tests_movimentacao_bloqueio import SetupMovimentacaoData


# ---------------------------------------------------------------------------
# Helpers genéricos
# ---------------------------------------------------------------------------


def _add_messages_support(request):
    """
    Adiciona suporte a mensagens no request (para testar actions do admin).
    """
    setattr(request, "session", "session")
    storage = FallbackStorage(request)
    setattr(request, "_messages", storage)
    return storage


class _DummyForm:
    def __init__(self, cleaned_data, instance=None):
        self.cleaned_data = cleaned_data
        self.instance = instance


class _DummyFormWrapper:
    """
    Wrapper mínimo para passar para o ModelAdmin.save_related.
    Precisa de 'instance' e de um método save_m2m().
    """

    def __init__(self, instance):
        self.instance = instance

    def save_m2m(self):
        # Nos testes não precisamos salvar m2m de nada.
        pass


class _DummyFormset:
    model = BaixaFisicaBensItem

    def __init__(self, deleted=None, new=None, instance=None):
        self.deleted_objects = deleted or []
        self.new_objects = new or []
        self.instance = instance

    def save(self):
        return


# ---------------------------------------------------------------------------
# Testes do modelo BaixaFisicaBemPatrimonial (clean, enviar, aprovar)
# ---------------------------------------------------------------------------


class BaixaFisicaModelCleanTestCase(TestCase):
    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_destino)

        # bem aprovado na UA de origem
        self.bem = setup.create_bem_patrimonial(self.operador_origem, self.ua_origem)
        self.bem.status = APROVADO
        self.bem.save()

    def _cria_baixa_com_item(self, status=AGUARDANDO_ENVIO, bem=None, data_baixa=None):
        bem = bem or self.bem
        baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            numero_processo_baixa="PROC-123",
            status=status,
            criado_por=self.operador_origem,
            data_baixa=data_baixa or timezone.localdate(),
        )
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=bem)
        return baixa

    def test_clean_exige_numero_processo(self):
        baixa = BaixaFisicaBemPatrimonial(
            unidade_administrativa_origem=self.ua_origem,
            criado_por=self.operador_origem,
            data_baixa=timezone.localdate(),
        )
        with self.assertRaises(ValidationError) as ctx:
            baixa.clean()
        self.assertIn("numero_processo_baixa", ctx.exception.message_dict)

    def test_clean_exige_itens_para_baixa_existente(self):
        baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            numero_processo_baixa="PROC-123",
            status=AGUARDANDO_ENVIO,
            criado_por=self.operador_origem,
            data_baixa=timezone.localdate(),
        )
        with self.assertRaises(ValidationError) as ctx:
            baixa.clean()
        self.assertIn("Baixa Física sem itens", str(ctx.exception))

    def test_clean_valida_unidade_administrativa_do_bem(self):
        # bem em outra UA
        bem_outra_ua = BemPatrimonial.objects.create(
            nome="Bem outra UA",
            descricao="X",
            numero_processo="123",
            valor_unitario=10,
            marca="M",
            modelo="MOD",
            numero_patrimonial="001.000000001-1",
            unidade_administrativa=self.ua_destino,
            status=APROVADO,
            criado_por=self.operador_destino,
        )
        baixa = self._cria_baixa_com_item(bem=bem_outra_ua)

        with self.assertRaises(ValidationError) as ctx:
            baixa.clean()
        self.assertIn(
            "não pertence à Unidade Administrativa selecionada", str(ctx.exception)
        )

    def test_clean_impede_bem_ja_baixado(self):
        self.bem.status = BAIXA_FISICA
        self.bem.save()

        baixa = self._cria_baixa_com_item()
        with self.assertRaises(ValidationError) as ctx:
            baixa.clean()
        self.assertIn("já foi baixado", str(ctx.exception))

    def test_clean_impede_bem_em_outra_baixa_em_andamento(self):
        # primeira baixa enviada
        baixa1 = self._cria_baixa_com_item(status=SOLICITADA)
        baixa1.clean()  # não deve levantar erro

        # segunda baixa com o mesmo bem
        baixa2 = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            numero_processo_baixa="PROC-456",
            status=AGUARDANDO_ENVIO,
            criado_por=self.operador_origem,
            data_baixa=timezone.localdate(),
        )
        BaixaFisicaBensItem.objects.create(baixa=baixa2, bem=self.bem)

        with self.assertRaises(ValidationError) as ctx:
            baixa2.clean()
        self.assertIn(
            "já está em processo de Baixa Física em outro pedido", str(ctx.exception)
        )

    def test_clean_nao_bloqueia_bem_na_mesma_baixa(self):
        # mesmo bem, mesma baixa – deve passar
        baixa = self._cria_baixa_com_item()
        try:
            baixa.clean()
        except ValidationError:
            self.fail("clean() não deveria falhar quando o bem está na mesma baixa.")


class BaixaFisicaFluxoEnvioAprovacaoTestCase(TestCase):
    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_destino)

        self.bem = setup.create_bem_patrimonial(self.operador_origem, self.ua_origem)
        self.bem.status = APROVADO
        self.bem.save()

        self.baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            numero_processo_baixa="PROC-123",
            status=AGUARDANDO_ENVIO,
            criado_por=self.operador_origem,
        )
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)

    def test_enviar_solicitacao_exige_itens(self):
        baixa_sem_itens = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            numero_processo_baixa="PROC-999",
            status=AGUARDANDO_ENVIO,
            criado_por=self.operador_origem,
        )

        with self.assertRaises(ValidationError):
            baixa_sem_itens.enviar_solicitacao()

    def test_enviar_solicitacao_muda_status_baixa_e_bem(self):
        self.assertEqual(self.baixa.status, AGUARDANDO_ENVIO)
        self.assertEqual(self.bem.status, APROVADO)

        self.baixa.enviar_solicitacao()
        self.baixa.refresh_from_db()
        self.bem.refresh_from_db()

        self.assertEqual(self.baixa.status, SOLICITADA)
        self.assertEqual(self.bem.status, BAIXA_FISICA_AGUARDANDO_APROVACAO)

    def test_aprovar_somente_quando_enviada(self):
        # status diferente de ENVIADA
        self.baixa.status = AGUARDANDO_ENVIO
        self.baixa.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            self.baixa.aprovar(self.gestor)

    def test_aprovar_atualiza_statuses_e_dados(self):
        # primeiro envia
        self.baixa.enviar_solicitacao()
        self.baixa.refresh_from_db()

        self.baixa.aprovar(self.gestor)
        self.baixa.refresh_from_db()
        self.bem.refresh_from_db()

        self.assertEqual(self.baixa.status, ACEITA)
        self.assertEqual(self.baixa.aprovado_por, self.gestor)
        self.assertIsNotNone(self.baixa.data_aprovacao)
        self.assertEqual(self.bem.status, BAIXA_FISICA)
        self.assertIsNone(self.bem.numero_processo)


# ---------------------------------------------------------------------------
# Testes do FormSet de itens (mínimo 1 bem)
# ---------------------------------------------------------------------------


class BaixaFisicaItensFormSetTestCase(TestCase):
    def test_clean_exige_ao_menos_um_bem_nao_deletado(self):
        with patch(
            "bem_patrimonial.admins.baixa_fisica_bem_patrimonial.BaseInlineFormSet.clean",
            lambda self: None,
        ):
            fs = BaixaFisicaBensItemInlineFormSet.__new__(
                BaixaFisicaBensItemInlineFormSet
            )

            # Caso 1: todos deletados ou sem bem -> deve lançar ValidationError
            fs.forms = [
                _DummyForm({"DELETE": True, "bem": None}),
                _DummyForm({"DELETE": False, "bem": None}),
            ]
            with self.assertRaises(ValidationError) as ctx:
                fs.clean()
            self.assertIn("Informe ao menos um bem", str(ctx.exception))

            # Caso 2: pelo menos um bem válido -> não deve lançar erro
            bem = BemPatrimonial(
                nome="Teste",
                descricao="x",
                numero_processo="1",
                valor_unitario=1,
                marca="M",
                modelo="MDL",
            )
            fs.forms = [
                _DummyForm({"DELETE": True, "bem": None}),
                _DummyForm({"DELETE": False, "bem": bem}),
            ]

            # não deve levantar exceção
            fs.clean()


# ---------------------------------------------------------------------------
# Testes do Admin (save_related + actions + queryset/permissions)
# ---------------------------------------------------------------------------


class BaixaFisicaAdminSaveRelatedTestCase(TestCase):
    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, _ = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            _,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_origem)

        # dois bens
        self.bem1 = setup.create_bem_patrimonial(self.operador_origem, self.ua_origem)
        self.bem2 = setup.create_bem_patrimonial(self.operador_origem, self.ua_origem)
        self.bem1.status = BAIXA_FISICA_AGUARDANDO_APROVACAO
        self.bem2.status = APROVADO
        self.bem1.save()
        self.bem2.save()

        self.baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            numero_processo_baixa="PROC-123",
            status=AGUARDANDO_ENVIO,
            criado_por=self.operador_origem,
        )
        self.item1 = BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem1)

        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = BaixaFisicaBemPatrimonialAdmin(
            BaixaFisicaBemPatrimonial, self.site
        )

    def test_save_related_ao_remover_item_reseta_status_bem(self):
        request = self.factory.post("/admin/")
        form = _DummyFormWrapper(self.baixa)

        formset = _DummyFormset(
            deleted=[self.item1],
            new=[],
            instance=self.baixa,
        )

        self.admin.save_related(request, form, [formset], change=True)

        self.bem1.refresh_from_db()
        self.assertEqual(self.bem1.status, APROVADO)

    def test_save_related_ao_adicionar_item_marca_bem_como_aguardando_aprovacao(self):
        request = self.factory.post("/admin/")
        form = _DummyFormWrapper(self.baixa)

        novo_item = BaixaFisicaBensItem(baixa=self.baixa, bem=self.bem2)
        formset = _DummyFormset(
            deleted=[],
            new=[novo_item],
            instance=self.baixa,
        )

        self.admin.save_related(request, form, [formset], change=True)

        self.bem2.refresh_from_db()
        self.assertEqual(self.bem2.status, BAIXA_FISICA_AGUARDANDO_APROVACAO)

    def test_save_related_nao_altera_bens_quando_status_nao_aguardando_envio(self):
        self.baixa.status = ENVIADA
        self.baixa.save(update_fields=["status"])

        request = self.factory.post("/admin/")
        form = _DummyFormWrapper(self.baixa)

        novo_item = BaixaFisicaBensItem(baixa=self.baixa, bem=self.bem2)
        formset = _DummyFormset(
            deleted=[self.item1],
            new=[novo_item],
            instance=self.baixa,
        )

        self.admin.save_related(request, form, [formset], change=True)

        # nada muda
        self.bem1.refresh_from_db()
        self.bem2.refresh_from_db()
        self.assertEqual(self.bem1.status, BAIXA_FISICA_AGUARDANDO_APROVACAO)
        self.assertEqual(self.bem2.status, APROVADO)


class BaixaFisicaAdminActionsTestCase(TestCase):
    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, _ = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            _,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_origem)

        self.bem = setup.create_bem_patrimonial(self.operador_origem, self.ua_origem)
        self.bem.status = APROVADO
        self.bem.save()

        self.baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            numero_processo_baixa="PROC-123",
            status=AGUARDANDO_ENVIO,
            criado_por=self.operador_origem,
        )
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)

        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = BaixaFisicaBemPatrimonialAdmin(
            BaixaFisicaBemPatrimonial, self.site
        )

    def _request(self, user):
        request = self.factory.post("/admin/")
        request.user = user
        _add_messages_support(request)
        return request

    def test_acao_enviar_baixa_dispara_enviar_solicitacao(self):
        request = self._request(self.operador_origem)
        qs = BaixaFisicaBemPatrimonial.objects.filter(pk=self.baixa.pk)

        self.admin.acao_enviar_baixa(request, qs)

        self.baixa.refresh_from_db()
        self.bem.refresh_from_db()
        self.assertEqual(self.baixa.status, SOLICITADA)
        self.assertEqual(self.bem.status, BAIXA_FISICA_AGUARDANDO_APROVACAO)

    def test_acao_aprovar_baixa_somente_para_gestor(self):
        request_op = self._request(self.operador_origem)
        qs = BaixaFisicaBemPatrimonial.objects.filter(pk=self.baixa.pk)

        # primeiro envia
        self.baixa.enviar_solicitacao()
        self.baixa.refresh_from_db()

        # operador NÃO pode aprovar
        self.admin.acao_aprovar_baixa(request_op, qs)
        self.baixa.refresh_from_db()
        self.assertNotEqual(self.baixa.status, ACEITA)

        # gestor pode
        request_gestor = self._request(self.gestor)
        self.admin.acao_aprovar_baixa(request_gestor, qs)

        self.baixa.refresh_from_db()
        self.bem.refresh_from_db()
        self.assertEqual(self.baixa.status, ACEITA)
        self.assertEqual(self.bem.status, BAIXA_FISICA)

    def test_acao_cancelar_baixa_reseta_status_bem(self):
        # simula baixa enviada (bens aguardando aprovação)
        self.baixa.enviar_solicitacao()
        self.baixa.refresh_from_db()
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, BAIXA_FISICA_AGUARDANDO_APROVACAO)

        request = self._request(self.gestor)
        qs = BaixaFisicaBemPatrimonial.objects.filter(pk=self.baixa.pk)

        self.admin.acao_cancelar_baixa(request, qs)

        self.baixa.refresh_from_db()
        self.bem.refresh_from_db()
        self.assertEqual(self.baixa.status, RECUSADA)
        self.assertEqual(self.bem.status, APROVADO)

    def test_acao_cancelar_nao_cancela_baixas_aceitas(self):
        # envia e aprova
        self.baixa.enviar_solicitacao()
        self.baixa.aprovar(self.gestor)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, ACEITA)

        request = self._request(self.gestor)
        qs = BaixaFisicaBemPatrimonial.objects.filter(pk=self.baixa.pk)

        self.admin.acao_cancelar_baixa(request, qs)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, ACEITA)


class BaixaFisicaAdminQuerysetPermissionsTestCase(TestCase):
    def setUp(self):
        setup = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = setup.create_unidades_administrativas()
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = setup.create_usuarios(self.ua_origem, self.ua_destino)

        self.baixa1 = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            numero_processo_baixa="PROC-111",
            status=AGUARDANDO_ENVIO,
            criado_por=self.operador_origem,
        )
        self.baixa2 = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_destino,
            numero_processo_baixa="PROC-222",
            status=AGUARDANDO_ENVIO,
            criado_por=self.operador_destino,
        )

        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = BaixaFisicaBemPatrimonialAdmin(
            BaixaFisicaBemPatrimonial, self.site
        )

    def test_get_queryset_filtra_por_unidade_do_usuario(self):
        request = self.factory.get("/admin/")
        request.user = self.operador_origem

        qs = self.admin.get_queryset(request)
        self.assertIn(self.baixa1, qs)
        self.assertNotIn(self.baixa2, qs)

    def test_get_queryset_gestor_sem_ua_ve_todas(self):
        # remove vinculo de UA do gestor
        self.gestor.unidade_administrativa = None

        self.gestor.save(update_fields=["unidade_administrativa"])

        request = self.factory.get("/admin/")
        request.user = self.gestor

        qs = self.admin.get_queryset(request)
        self.assertIn(self.baixa1, qs)
        self.assertIn(self.baixa2, qs)

    def test_changelist_view_operador_sem_ua_exibe_warning(self):
        # operador sem UA não deve ver nada e recebe aviso
        self.operador_origem.unidade_administrativa = None
        self.operador_origem.save(update_fields=["unidade_administrativa"])

        request = self.factory.get("/admin/")
        request.user = self.operador_origem
        storage = _add_messages_support(request)

        self.admin.changelist_view(request)

        msgs = [str(m) for m in storage]
        self.assertTrue(
            any(
                "Como operador você deve estár vinculado a uma unidade administrativa"
                in m
                for m in msgs
            )
        )
