from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua
from django.test import TestCase, RequestFactory
from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib import messages
from unittest.mock import Mock, patch

from bem_patrimonial.models import (
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
    MovimentacaoBensItem,
)
from bem_patrimonial.constants import (
    APROVADO,
    BLOQUEADO,
    ENVIADA,
    ACEITA,
    CANCELADA,
    REJEITADA,
)
from bem_patrimonial.admins.movimentacao_bem_patrimonial import (
    MovimentacaoBemPatrimonialAdmin,
    aprovar_solicitacao,
    cancelar_solicitacao,
    rejeitar_solicitacao,
)
from bem_patrimonial.admins.forms.movimentacao_bem_patrimonial_form import (
    obter_ua_ponto_central,
)
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_OPERADOR_INVENTARIO, GRUPO_GESTOR_PATRIMONIO
from django.contrib.auth.models import Group


class SetupMovimentacaoData:
    def create_unidades_administrativas(self):
        ua_origem = criar_ua()
        ua_destino = criar_ua(
            uo=ua_origem.unidade_orcamentaria, nome="DRE Sul", codigo="DRE-SUL"
        )
        return ua_origem, ua_destino

    def create_usuarios(self, ua_origem, ua_destino):
        grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)

        operador_origem = Usuario.objects.create_user(
            username="operador_origem",
            email="operador.origem@test.com",
            **auth_kwargs("test123"),
            unidade_orcamentaria=ua_origem.unidade_orcamentaria,
            unidade_administrativa=ua_origem,
        )
        operador_origem.groups.add(grupo_operador)
        operador_origem.unidades_administrativas.add(ua_origem)

        operador_destino = Usuario.objects.create_user(
            username="operador_destino",
            email="operador.destino@test.com",
            **auth_kwargs("test123"),
            unidade_administrativa=ua_destino,
            unidade_orcamentaria=ua_destino.unidade_orcamentaria,
        )
        operador_destino.groups.add(grupo_operador)
        operador_destino.unidades_administrativas.add(ua_destino)

        gestor = Usuario.objects.create_user(
            username="gestor",
            email="gestor@test.com",
            **auth_kwargs("test123"),
            is_staff=True,
            is_superuser=True,
            unidade_administrativa=ua_origem,
            unidade_orcamentaria=ua_origem.unidade_orcamentaria,
        )
        gestor.groups.add(grupo_gestor)

        return operador_origem, operador_destino, gestor

    def create_bem_patrimonial(
        self,
        criado_por,
        ua_origem,
        *,
        numero_patrimonial=None,
        sem_numeracao=False,
    ):
        if numero_patrimonial is None and not sem_numeracao:
            base = 1
            while True:
                candidato = f"000.{str(base).zfill(12)}-0"
                if not BemPatrimonial.objects.filter(
                    numero_patrimonial=candidato
                ).exists():
                    numero_patrimonial = candidato
                    break
                base += 1

        bem = BemPatrimonial.objects.create(
            nome="Notebook Dell",
            descricao="Notebook Dell Inspiron 15",
            numero_processo="PROC-123456",
            valor_unitario=3500.00,
            marca="Dell",
            modelo="Inspiron 15",
            numero_patrimonial=numero_patrimonial,
            numero_formato_antigo=False,
            sem_numeracao=sem_numeracao,
            localizacao="Almoxarifado",
            criado_por=criado_por,
            status=APROVADO,
            unidade_administrativa=ua_origem,
        )
        return bem

    def create_movimentacao_com_item(
        self,
        bem,
        ua_origem,
        ua_destino,
        solicitado_por,
    ):
        """
        Helper para criar movimentação já com um item vinculado.
        Isso garante que as regras que usam mov.itens funcionem.
        """
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=ua_origem,
            unidade_administrativa_destino=ua_destino,
            solicitado_por=solicitado_por,
        )
        MovimentacaoBensItem.objects.create(
            movimentacao=mov,
            bem=bem,
        )
        return mov


def codigo_uo(a, b, c):
    return f"{int(a):02d}.{int(b):02d}.{int(c):02d}"


class BloqueioAutomaticoTestCase(TestCase):
    def setUp(self):
        self.test_data = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = (
            self.test_data.create_unidades_administrativas()
        )
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = self.test_data.create_usuarios(self.ua_origem, self.ua_destino)
        self.bem = self.test_data.create_bem_patrimonial(
            self.operador_origem, self.ua_origem
        )

    def test_bem_bloqueado_ao_criar_movimentacao(self):
        self.assertEqual(self.bem.status, APROVADO)

        movimentacao = self.test_data.create_movimentacao_com_item(
            bem=self.bem,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, BLOQUEADO)
        self.assertEqual(movimentacao.status, ENVIADA)

    def test_property_tem_movimentacao_pendente(self):
        self.assertFalse(self.bem.tem_movimentacao_pendente)

        self.test_data.create_movimentacao_com_item(
            bem=self.bem,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        self.bem.refresh_from_db()
        self.assertTrue(self.bem.tem_movimentacao_pendente)

    def test_property_pode_solicitar_movimentacao(self):
        self.assertTrue(self.bem.pode_solicitar_movimentacao)

        self.bem.status = BLOQUEADO
        self.bem.save()

        self.assertFalse(self.bem.pode_solicitar_movimentacao)


class AprovacaoMovimentacaoTestCase(TestCase):
    def setUp(self):
        self.test_data = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = (
            self.test_data.create_unidades_administrativas()
        )
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = self.test_data.create_usuarios(self.ua_origem, self.ua_destino)
        self.bem = self.test_data.create_bem_patrimonial(
            self.operador_origem, self.ua_origem
        )

        self.movimentacao = self.test_data.create_movimentacao_com_item(
            bem=self.bem,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

    def test_aprovar_movimentacao_move_bem_para_ua_destino(self):
        self.movimentacao.aprovar_solicitacao(self.operador_destino)

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.unidade_administrativa, self.ua_destino)

    def test_aprovar_movimentacao_desbloqueia_bem(self):
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, BLOQUEADO)

        self.movimentacao.aprovar_solicitacao(self.operador_destino)

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, APROVADO)

    def test_aprovar_movimentacao_muda_status(self):
        self.assertEqual(self.movimentacao.status, ENVIADA)

        self.movimentacao.aprovar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        self.assertEqual(self.movimentacao.status, ACEITA)
        self.assertEqual(self.movimentacao.aprovado_por, self.operador_destino)

    def test_property_aceita(self):
        self.assertFalse(self.movimentacao.aceita)

        self.movimentacao.aprovar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        self.assertTrue(self.movimentacao.aceita)


class RejeicaoMovimentacaoTestCase(TestCase):
    def setUp(self):
        self.test_data = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = (
            self.test_data.create_unidades_administrativas()
        )
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = self.test_data.create_usuarios(self.ua_origem, self.ua_destino)
        self.bem = self.test_data.create_bem_patrimonial(
            self.operador_origem, self.ua_origem
        )

        self.movimentacao = self.test_data.create_movimentacao_com_item(
            bem=self.bem,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

    def test_rejeitar_movimentacao_nao_altera_ua_do_bem(self):
        ua_inicial = self.bem.unidade_administrativa

        self.movimentacao.rejeitar_solicitacao(self.operador_destino)
        self.bem.refresh_from_db()

        self.assertEqual(self.bem.unidade_administrativa, ua_inicial)

    def test_rejeitar_movimentacao_desbloqueia_bem(self):
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, BLOQUEADO)

        self.movimentacao.rejeitar_solicitacao(self.operador_destino)

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, APROVADO)

    def test_rejeitar_movimentacao_muda_status(self):
        self.assertEqual(self.movimentacao.status, ENVIADA)

        self.movimentacao.rejeitar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        self.assertEqual(self.movimentacao.status, REJEITADA)
        self.assertEqual(self.movimentacao.rejeitado_por, self.operador_destino)

    def test_property_rejeitada(self):
        self.assertFalse(self.movimentacao.rejeitada)

        self.movimentacao.rejeitar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        self.assertTrue(self.movimentacao.rejeitada)


class PermissoesAdminActionsTestCase(TestCase):
    def setUp(self):
        self.test_data = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = (
            self.test_data.create_unidades_administrativas()
        )
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = self.test_data.create_usuarios(self.ua_origem, self.ua_destino)
        self.bem = self.test_data.create_bem_patrimonial(
            self.operador_origem, self.ua_origem
        )

        self.movimentacao = self.test_data.create_movimentacao_com_item(
            bem=self.bem,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = MovimentacaoBemPatrimonialAdmin(
            MovimentacaoBemPatrimonial, self.site
        )

    def _create_request_with_messages(self, user):
        request = self.factory.post("/admin/")
        request.user = user
        setattr(request, "session", "session")
        messages_storage = FallbackStorage(request)
        setattr(request, "_messages", messages_storage)
        return request

    def test_operador_origem_nao_pode_aprovar(self):
        request = self._create_request_with_messages(self.operador_origem)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ENVIADA)
        self.assertIsNone(self.movimentacao.aprovado_por)

    def test_operador_destino_pode_aprovar(self):
        request = self._create_request_with_messages(self.operador_destino)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ACEITA)
        self.assertEqual(self.movimentacao.aprovado_por, self.operador_destino)

    def test_gestor_pode_aprovar(self):
        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ACEITA)
        self.assertEqual(self.movimentacao.aprovado_por, self.gestor)

    def test_gestor_pode_aprovar_propria_solicitacao_na_mesma_uo(self):
        movimentacao = self.test_data.create_movimentacao_com_item(
            bem=self.bem,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.gestor,
        )

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        movimentacao.refresh_from_db()
        self.assertEqual(movimentacao.status, ACEITA)
        self.assertEqual(movimentacao.aprovado_por, self.gestor)

    def test_gestor_pode_rejeitar_propria_solicitacao_na_mesma_uo(self):
        movimentacao = self.test_data.create_movimentacao_com_item(
            bem=self.bem,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.gestor,
        )

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=movimentacao.pk)

        rejeitar_solicitacao(self.admin, request, queryset)

        movimentacao.refresh_from_db()
        self.assertEqual(movimentacao.status, REJEITADA)
        self.assertEqual(movimentacao.rejeitado_por, self.gestor)

    def test_solicitante_nao_pode_aprovar_propria_solicitacao(self):
        self.bem.unidade_administrativa = self.ua_destino
        self.bem.save()

        movimentacao2 = self.test_data.create_movimentacao_com_item(
            bem=self.bem,
            ua_origem=self.ua_destino,
            ua_destino=self.ua_origem,
            solicitado_por=self.operador_destino,
        )

        request = self._create_request_with_messages(self.operador_destino)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=movimentacao2.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        movimentacao2.refresh_from_db()
        self.assertEqual(movimentacao2.status, ENVIADA)
        self.assertIsNone(movimentacao2.aprovado_por)

    def test_action_com_multiplas_movimentacoes(self):
        bem2 = self.test_data.create_bem_patrimonial(self.gestor, self.ua_origem)
        movimentacao2 = self.test_data.create_movimentacao_com_item(
            bem=bem2,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        request = self._create_request_with_messages(self.operador_destino)
        queryset = MovimentacaoBemPatrimonial.objects.filter(
            pk__in=[self.movimentacao.pk, movimentacao2.pk]
        )

        aprovar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        movimentacao2.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ACEITA)
        self.assertEqual(movimentacao2.status, ACEITA)

    def test_nao_pode_aprovar_movimentacao_ja_aprovada(self):
        self.movimentacao.aprovar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        self.assertTrue(
            any("já foi aprovada anteriormente" in msg for msg in mensagens)
        )

    def test_nao_pode_rejeitar_movimentacao_ja_rejeitada(self):
        self.movimentacao.rejeitar_solicitacao(self.operador_destino)
        self.movimentacao.refresh_from_db()

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        rejeitar_solicitacao(self.admin, request, queryset)

        storage = messages.get_messages(request)
        mensagens = [str(m) for m in storage]
        self.assertTrue(
            any("já foi rejeitada anteriormente" in msg for msg in mensagens)
        )

    def test_operador_fora_da_ua_destino_nao_pode_rejeitar(self):
        request = self._create_request_with_messages(self.operador_origem)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)

        rejeitar_solicitacao(self.admin, request, queryset)

        self.movimentacao.refresh_from_db()
        self.assertEqual(self.movimentacao.status, ENVIADA)
        mensagens = [str(m) for m in messages.get_messages(request)]
        self.assertTrue(any("Apenas operadores da unidade de destino" in msg for msg in mensagens))

    def test_solicitante_nao_pode_rejeitar_propria_solicitacao(self):
        movimentacao2 = self.test_data.create_movimentacao_com_item(
            bem=self.bem,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_destino,
        )

        request = self._create_request_with_messages(self.operador_destino)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=movimentacao2.pk)

        rejeitar_solicitacao(self.admin, request, queryset)

        movimentacao2.refresh_from_db()
        self.assertEqual(movimentacao2.status, ENVIADA)
        mensagens = [str(m) for m in messages.get_messages(request)]
        self.assertTrue(any("Você não pode rejeitar sua própria solicitação" in msg for msg in mensagens))

    def test_aprovar_movimentacao_sem_itens_exibe_erro(self):
        movimentacao_sem_itens = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=movimentacao_sem_itens.pk)

        aprovar_solicitacao(self.admin, request, queryset)

        mensagens = [str(m) for m in messages.get_messages(request)]
        self.assertTrue(any("não possui bens associados" in msg for msg in mensagens))

    def test_rejeitar_movimentacao_sem_itens_exibe_erro(self):
        movimentacao_sem_itens = MovimentacaoBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        request = self._create_request_with_messages(self.gestor)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=movimentacao_sem_itens.pk)

        rejeitar_solicitacao(self.admin, request, queryset)

        mensagens = [str(m) for m in messages.get_messages(request)]
        self.assertTrue(any("não possui bens associados" in msg for msg in mensagens))

    def test_get_documento_cimbpm_link_sem_numero(self):
        self.movimentacao.numero_cimbpm = ""
        self.movimentacao.save(update_fields=["numero_cimbpm"])

        self.assertEqual(
            self.admin.get_documento_cimbpm_link(self.movimentacao),
            "Número CIMBPM não gerado",
        )

    def test_get_documento_cimbpm_link_com_numero(self):
        resultado = self.admin.get_documento_cimbpm_link(self.movimentacao)
        self.assertIn("Baixar Documento CIMBPM", str(resultado))

    def test_get_unidade_orcamentaria_destino_sem_destino(self):
        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            solicitado_por=self.operador_origem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
        )
        movimentacao.unidade_administrativa_destino = None
        movimentacao.unidade_administrativa_destino_id = None
        self.assertEqual(self.admin.get_unidade_orcamentaria_destino(movimentacao), "-")

    @patch("bem_patrimonial.admins.movimentacao_bem_patrimonial.verificar_movimentacoes_duplicadas")
    def test_response_action_verificar_movimentacoes_duplicadas(self, mock_verificar):
        request = self._create_request_with_messages(self.gestor)
        request.POST = request.POST.copy()
        request.POST["action"] = "verificar_movimentacoes_duplicadas"
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=self.movimentacao.pk)
        mock_changelist = Mock()
        mock_changelist.get_queryset.return_value = queryset
        self.admin.get_changelist_instance = Mock(return_value=mock_changelist)
        mock_verificar.return_value = "ok"

        resposta = self.admin.response_action(request, queryset)

        self.assertEqual(resposta, "ok")
        mock_verificar.assert_called_once_with(self.admin, request, queryset)

    @patch("django.contrib.admin.options.ModelAdmin.get_inline_formsets")
    def test_get_inline_formsets_desabilita_campos_na_edicao(self, mock_super_get_inline_formsets):
        campo = Mock()
        form = Mock(fields={"bem": campo, "descricao": Mock()})
        formset = Mock(can_add=True, can_delete=True, forms=[form])
        mock_super_get_inline_formsets.return_value = [formset]

        retorno = self.admin.get_inline_formsets(
            request=self._create_request_with_messages(self.gestor),
            formsets=[],
            inline_instances=[],
            obj=self.movimentacao,
        )

        self.assertEqual(retorno, [formset])
        self.assertFalse(formset.can_add)
        self.assertFalse(formset.can_delete)
        self.assertTrue(all(field.disabled for field in form.fields.values()))


class IntegracaoCompletaTestCase(TestCase):
    def setUp(self):
        self.test_data = SetupMovimentacaoData()
        self.ua_origem, self.ua_destino = (
            self.test_data.create_unidades_administrativas()
        )
        (
            self.operador_origem,
            self.operador_destino,
            self.gestor,
        ) = self.test_data.create_usuarios(self.ua_origem, self.ua_destino)
        self.bem = self.test_data.create_bem_patrimonial(
            self.operador_origem, self.ua_origem
        )

    def test_fluxo_completo_aprovacao(self):
        self.assertEqual(self.bem.status, APROVADO)
        self.assertFalse(self.bem.tem_movimentacao_pendente)

        movimentacao = self.test_data.create_movimentacao_com_item(
            bem=self.bem,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, BLOQUEADO)
        self.assertTrue(self.bem.tem_movimentacao_pendente)
        self.assertEqual(movimentacao.status, ENVIADA)

        movimentacao.aprovar_solicitacao(self.operador_destino)
        movimentacao.refresh_from_db()
        self.bem.refresh_from_db()

        self.assertEqual(movimentacao.status, ACEITA)
        self.assertEqual(self.bem.status, APROVADO)
        self.assertFalse(self.bem.tem_movimentacao_pendente)
        self.assertEqual(self.bem.unidade_administrativa, self.ua_destino)

    def test_fluxo_completo_rejeicao(self):
        ua_inicial = self.bem.unidade_administrativa

        movimentacao = self.test_data.create_movimentacao_com_item(
            bem=self.bem,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, BLOQUEADO)

        movimentacao.rejeitar_solicitacao(self.operador_destino)
        movimentacao.refresh_from_db()
        self.bem.refresh_from_db()

        self.assertEqual(movimentacao.status, REJEITADA)
        self.assertEqual(self.bem.status, APROVADO)
        self.assertFalse(self.bem.tem_movimentacao_pendente)

        self.assertEqual(self.bem.unidade_administrativa, ua_inicial)

    def test_multiplas_movimentacoes_sequenciais(self):

        mov1 = self.test_data.create_movimentacao_com_item(
            bem=self.bem,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )
        mov1.aprovar_solicitacao(self.operador_destino)
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.unidade_administrativa, self.ua_destino)

        mov2 = self.test_data.create_movimentacao_com_item(
            bem=self.bem,
            ua_origem=self.ua_destino,
            ua_destino=self.ua_origem,
            solicitado_por=self.operador_destino,
        )
        mov2.aprovar_solicitacao(self.operador_origem)

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.unidade_administrativa, self.ua_origem)

    def test_aprovacao_para_outra_uo_move_bem_para_ua_ponto_central(self):
        uo_destino_externa = criar_uo(
            codigo=codigo_uo(1, 16, 11),
            nome="UO Destino Externa",
            sigla="UO5",
        )
        criar_ua(
            uo=uo_destino_externa,
            codigo=codigo_ua(1, 16, 11, 1),
            nome="Ponto Central Externo",
            sigla="PCE",
        )
        ua_destino_externa = obter_ua_ponto_central(uo_destino_externa)

        movimentacao = self.test_data.create_movimentacao_com_item(
            bem=self.bem,
            ua_origem=self.ua_origem,
            ua_destino=ua_destino_externa,
            solicitado_por=self.operador_origem,
        )

        movimentacao.aprovar_solicitacao(self.gestor)
        self.bem.refresh_from_db()

        self.assertEqual(self.bem.unidade_administrativa, ua_destino_externa)


class PermissoesEntreUOsAdminActionsTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = MovimentacaoBemPatrimonialAdmin(
            MovimentacaoBemPatrimonial, self.site
        )

        self.grupo_operador, _ = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )
        self.grupo_gestor, _ = Group.objects.get_or_create(
            name=GRUPO_GESTOR_PATRIMONIO
        )

        self.uo_origem = criar_uo(
            codigo=codigo_uo(1, 16, 20),
            nome="UO Origem",
            sigla="UOOR",
        )
        self.ua_origem = criar_ua(
            uo=self.uo_origem,
            codigo=codigo_ua(1, 16, 20, 5),
            nome="UA Origem",
            sigla="UAOR",
        )
        self.ua_gestor_origem = criar_ua(
            uo=self.uo_origem,
            codigo=codigo_ua(1, 16, 20, 10),
            nome="UA Gestor Origem",
            sigla="UGOR",
        )

        self.uo_destino = criar_uo(
            codigo=codigo_uo(1, 16, 21),
            nome="UO Destino",
            sigla="UODE",
        )
        self.ua_destino_central = criar_ua(
            uo=self.uo_destino,
            codigo=codigo_ua(1, 16, 21, 1),
            nome="Ponto Central Destino",
            sigla="PCDE",
        )
        self.ua_gestor_destino = criar_ua(
            uo=self.uo_destino,
            codigo=codigo_ua(1, 16, 21, 10),
            nome="UA Gestor Destino",
            sigla="UGDE",
        )

        self.operador_origem = Usuario.objects.create_user(
            username="operador_origem_uo_diff",
            email="operador.origem.uo.diff@test.com",
            **auth_kwargs("test123"),
            unidade_orcamentaria=self.uo_origem,
            unidade_administrativa=self.ua_origem,
        )
        self.operador_origem.groups.add(self.grupo_operador)
        self.operador_origem.unidades_administrativas.add(self.ua_origem)

        self.operador_destino = Usuario.objects.create_user(
            username="operador_destino_uo_diff",
            email="operador.destino.uo.diff@test.com",
            **auth_kwargs("test123"),
            unidade_orcamentaria=self.uo_destino,
            unidade_administrativa=self.ua_destino_central,
        )
        self.operador_destino.groups.add(self.grupo_operador)
        self.operador_destino.unidades_administrativas.add(self.ua_destino_central)

        self.gestor_origem = self._create_gestor(
            username="gestor_origem_uo_diff",
            email="gestor.origem.uo.diff@test.com",
            unidade_orcamentaria=self.uo_origem,
            unidade_administrativa=self.ua_gestor_origem,
        )
        self.gestor_destino = self._create_gestor(
            username="gestor_destino_uo_diff",
            email="gestor.destino.uo.diff@test.com",
            unidade_orcamentaria=self.uo_destino,
            unidade_administrativa=self.ua_gestor_destino,
        )

        self.bem = BemPatrimonial.objects.create(
            nome="Notebook Inter UO",
            descricao="Notebook para testar movimentacao entre UOs",
            numero_processo="PROC-INTER-UO",
            valor_unitario=2500.00,
            marca="Dell",
            modelo="Latitude",
            numero_patrimonial="999.999999999-9",
            numero_formato_antigo=False,
            sem_numeracao=False,
            localizacao="Sala 1",
            criado_por=self.operador_origem,
            status=APROVADO,
            unidade_administrativa=self.ua_origem,
        )

        self.movimentacao = self._create_movimentacao(solicitado_por=self.operador_origem)

    def _create_gestor(
        self, username, email, unidade_orcamentaria, unidade_administrativa
    ):
        gestor = Usuario.objects.create_user(
            username=username,
            email=email,
            **auth_kwargs("test123"),
            is_staff=True,
            unidade_orcamentaria=unidade_orcamentaria,
            unidade_administrativa=unidade_administrativa,
        )
        gestor.groups.add(self.grupo_gestor)
        return gestor

    def _create_request_with_messages(self, user):
        request = self.factory.post("/admin/")
        request.user = user
        setattr(request, "session", "session")
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def _create_movimentacao(self, solicitado_por):
        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=self.bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino_central,
            solicitado_por=solicitado_por,
        )
        MovimentacaoBensItem.objects.create(
            movimentacao=movimentacao,
            bem=self.bem,
        )
        return movimentacao

    def _executar_acao(self, action, user, movimentacao=None):
        movimentacao = movimentacao or self.movimentacao
        request = self._create_request_with_messages(user)
        queryset = MovimentacaoBemPatrimonial.objects.filter(pk=movimentacao.pk)

        action(self.admin, request, queryset)
        movimentacao.refresh_from_db()
        return request, movimentacao

    def _assert_acao_bloqueada(self, action, user, mensagem, movimentacao=None):
        request, movimentacao = self._executar_acao(action, user, movimentacao)
        self.assertEqual(movimentacao.status, ENVIADA)
        mensagens = [str(item) for item in messages.get_messages(request)]
        self.assertTrue(any(mensagem in item for item in mensagens))

    def _assert_acao_permitida(
        self,
        action,
        user,
        expected_status,
        campo_usuario,
        movimentacao=None,
    ):
        _, movimentacao = self._executar_acao(action, user, movimentacao)
        self.assertEqual(movimentacao.status, expected_status)
        self.assertEqual(getattr(movimentacao, campo_usuario), user)

    def test_gestor_origem_nao_pode_aprovar_movimentacao_entre_uos(self):
        self._assert_acao_bloqueada(
            aprovar_solicitacao,
            self.gestor_origem,
            "Apenas gestores da UO de destino",
        )

    def test_gestor_origem_nao_pode_rejeitar_movimentacao_entre_uos(self):
        self._assert_acao_bloqueada(
            rejeitar_solicitacao,
            self.gestor_origem,
            "Apenas gestores da UO de destino",
        )

    def test_gestor_destino_pode_aprovar_movimentacao_entre_uos(self):
        self._assert_acao_permitida(
            aprovar_solicitacao,
            self.gestor_destino,
            ACEITA,
            "aprovado_por",
        )

    def test_gestor_destino_pode_rejeitar_movimentacao_entre_uos(self):
        self._assert_acao_permitida(
            rejeitar_solicitacao,
            self.gestor_destino,
            REJEITADA,
            "rejeitado_por",
        )

    @patch(
        "bem_patrimonial.admins.movimentacao_bem_patrimonial.envia_email_solicitacao_movimentacao_cancelada"
    )
    def test_gestor_origem_pode_cancelar_movimentacao_entre_uos(self, mock_email):
        self._assert_acao_permitida(
            cancelar_solicitacao,
            self.gestor_origem,
            CANCELADA,
            "cancelado_por",
        )
        mock_email.assert_called_once()

    @patch(
        "bem_patrimonial.admins.movimentacao_bem_patrimonial.envia_email_solicitacao_movimentacao_cancelada"
    )
    def test_gestor_destino_pode_cancelar_movimentacao_entre_uos(self, mock_email):
        self._assert_acao_permitida(
            cancelar_solicitacao,
            self.gestor_destino,
            CANCELADA,
            "cancelado_por",
        )
        mock_email.assert_called_once()

    def test_gestor_origem_nao_pode_aprovar_propria_movimentacao_entre_uos(self):
        movimentacao = self._create_movimentacao(solicitado_por=self.gestor_origem)
        self._assert_acao_bloqueada(
            aprovar_solicitacao,
            self.gestor_origem,
            "não pode aprovar sua própria solicitação em movimentações entre UOs",
            movimentacao,
        )

    def test_gestor_destino_nao_pode_rejeitar_propria_movimentacao_entre_uos(self):
        movimentacao = self._create_movimentacao(solicitado_por=self.gestor_destino)
        self._assert_acao_bloqueada(
            rejeitar_solicitacao,
            self.gestor_destino,
            "não pode rejeitar sua própria solicitação em movimentações entre UOs",
            movimentacao,
        )
