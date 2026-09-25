from unittest.mock import patch, MagicMock

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from dados_comuns.tests.auth_test_utils import auth_kwargs
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO

from bem_patrimonial.models import (
    BaixaFisicaBemPatrimonial,
    BaixaFisicaBensItem,
    BemPatrimonial,
    NBBPM,
)
from bem_patrimonial.api_serializers import (
    BaixaFisicaBemPatrimonialCreateSerializer,
    BaixaFisicaBemPatrimonialUpdateSerializer,
    BaixaFisicaBemPatrimonialDetailSerializer,
    BaixaFisicaAprovarSerializer,
    BaixaFisicaCancelarSerializer,
    BaixaFisicaSolicitarCorrecaoSerializer,
    BaixaFisicaEnviarSolicitacaoSerializer,
    BaixaFisicaBensItemCreateSerializer,
    UnidadeAdministrativaSimpleSerializer,
    UserSimpleSerializer,
    BemPatrimonialSimpleSerializer,
    NBBPMGerarLoteSerializer,
    NBBPMSerializer,
)
from bem_patrimonial import constants


# ============================================================================
# HELPERS / SETUP BASE
# ============================================================================

def criar_usuario(username, uo, ua, grupos=None, **kwargs):
    user = Usuario.objects.create_user(
        username=username,
        email=f"{username}@test.com",
        **auth_kwargs("senha123"),
        unidade_administrativa=ua,
        unidade_orcamentaria=uo,
        **kwargs,
    )
    for grupo_nome in (grupos or []):
        grupo, _ = Group.objects.get_or_create(name=grupo_nome)
        user.groups.add(grupo)
    return user


def criar_bem(ua, criado_por, numero_patrimonial="000.000000001-0", status=constants.APROVADO, **kwargs):
    return BemPatrimonial.objects.create(
        nome=kwargs.pop("nome", "Notebook Dell"),
        descricao=kwargs.pop("descricao", "Notebook para testes"),
        valor_unitario=kwargs.pop("valor_unitario", 1000),
        marca=kwargs.pop("marca", "Dell"),
        modelo=kwargs.pop("modelo", "Latitude"),
        numero_processo=kwargs.pop("numero_processo", "PROC-TESTE"),
        numero_patrimonial=numero_patrimonial,
        unidade_administrativa=ua,
        criado_por=criado_por,
        status=status,
        **kwargs,
    )


def criar_baixa(ua, criado_por, status=constants.AGUARDANDO_ENVIO, **kwargs):
    return BaixaFisicaBemPatrimonial.objects.create(
        unidade_administrativa_origem=ua,
        numero_processo_baixa=kwargs.pop("numero_processo_baixa", "PROC-BX-001"),
        status=status,
        criado_por=criado_por,
        data_baixa=kwargs.pop("data_baixa", timezone.localdate()),
        **kwargs,
    )


class BaseSetup(TestCase):
    def setUp(self):
        self.uo = criar_uo(codigo="100", nome="UO Teste", sigla="UOT")
        self.ua = criar_ua(uo=self.uo, codigo="001", nome="UA Teste", sigla="UAT")
        self.ua2 = criar_ua(uo=self.uo, codigo="002", nome="UA Dois", sigla="UAD")

        self.gestor = criar_usuario(
            "gestor_api", self.uo, self.ua,
            grupos=[GRUPO_GESTOR_PATRIMONIO],
            is_staff=True,
        )
        self.operador = criar_usuario(
            "operador_api", self.uo, self.ua,
            grupos=[GRUPO_OPERADOR_INVENTARIO],
        )
        self.operador2 = criar_usuario(
            "operador2_api", self.uo, self.ua2,
            grupos=[GRUPO_OPERADOR_INVENTARIO],
        )

        self.bem = criar_bem(self.ua, self.operador)
        self.bem2 = criar_bem(self.ua, self.operador, numero_patrimonial="000.000000002-0")


class BaseAPISetup(BaseSetup):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    @property
    def list_url(self):
        return reverse("baixas-fisicas-list")

    def detail_url(self, pk):
        return reverse("baixas-fisicas-detail", kwargs={"pk": pk})

    def action_url(self, pk, action):
        return reverse(f"baixas-fisicas-{action}", kwargs={"pk": pk})


# ============================================================================
# TESTES DE SERIALIZERS SIMPLES
# ============================================================================

class UnidadeAdministrativaSimpleSerializerTestCase(BaseSetup):
    def test_campos_retornados(self):
        data = UnidadeAdministrativaSimpleSerializer(self.ua).data
        for campo in ["id", "nome", "sigla", "codigo", "status"]:
            self.assertIn(campo, data)

    def test_valores_corretos(self):
        data = UnidadeAdministrativaSimpleSerializer(self.ua).data
        self.assertEqual(data["nome"], "UA Teste")
        self.assertEqual(data["sigla"], "UAT")


class UserSimpleSerializerTestCase(BaseSetup):
    def test_campos_retornados(self):
        data = UserSimpleSerializer(self.gestor).data
        for campo in ["id", "username", "nome_completo", "email", "rf"]:
            self.assertIn(campo, data)

    def test_expoe_rf_para_formato_nome_mais_rf(self):
        """O RF é necessário para o front montar "Nome Completo (RF 1234567)"."""
        self.gestor.rf = "F1234567"
        self.gestor.save()
        data = UserSimpleSerializer(self.gestor).data
        self.assertEqual(data["rf"], "F1234567")

    def test_rf_nulo_permanece_none(self):
        """RF é opcional no modelo; o serializer não deve inventar valor."""
        self.gestor.rf = None
        self.gestor.save()
        data = UserSimpleSerializer(self.gestor).data
        self.assertIsNone(data["rf"])

    def test_nome_completo_fallback_username(self):
        data = UserSimpleSerializer(self.gestor).data
        self.assertEqual(data["nome_completo"], self.gestor.username)

    def test_nome_completo_com_nome(self):
        self.gestor.first_name = "João"
        self.gestor.last_name = "Silva"
        self.gestor.save()
        data = UserSimpleSerializer(self.gestor).data
        self.assertIn("João", data["nome_completo"])


class BemPatrimonialSimpleSerializerTestCase(BaseSetup):
    def test_campos_retornados(self):
        data = BemPatrimonialSimpleSerializer(self.bem).data
        for campo in ["id", "numero_patrimonial", "nome", "descricao", "status"]:
            self.assertIn(campo, data)


# ============================================================================
# TESTES DE SERIALIZERS DE ITEM
# ============================================================================

class BaixaFisicaBensItemCreateSerializerTestCase(BaseSetup):
    def _serializer(self, bem, baixa_id=None):
        return BaixaFisicaBensItemCreateSerializer(
            data={"bem": bem.id if bem else None},
            context={"baixa_id": baixa_id},
        )

    def test_bem_valido(self):
        s = self._serializer(self.bem)
        self.assertTrue(s.is_valid(), s.errors)

    def test_sem_bem_invalido(self):
        s = BaixaFisicaBensItemCreateSerializer(data={})
        self.assertFalse(s.is_valid())

    def test_bem_em_outra_baixa_pendente_invalido(self):
        outra_baixa = criar_baixa(self.ua, self.operador, status=constants.AGUARDANDO_ENVIO)
        BaixaFisicaBensItem.objects.create(baixa=outra_baixa, bem=self.bem)
        self.bem.status = constants.BAIXA_FISICA_AGUARDANDO_APROVACAO
        self.bem.save()

        s = self._serializer(self.bem, baixa_id=None)
        self.assertFalse(s.is_valid())
        self.assertIn("bem", s.errors)

    def test_bem_em_mesma_baixa_nao_bloqueia(self):
        baixa = criar_baixa(self.ua, self.operador)
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        self.bem.status = constants.BAIXA_FISICA_AGUARDANDO_APROVACAO
        self.bem.save()

        s = self._serializer(self.bem, baixa_id=baixa.id)
        self.assertTrue(s.is_valid(), s.errors)


# ============================================================================
# TESTES DE SERIALIZER DE CRIAÇÃO
# ============================================================================

class BaixaFisicaBemPatrimonialCreateSerializerTestCase(BaseSetup):
    def _req(self):
        req = MagicMock()
        req.user = self.operador
        return req

    def _data(self, itens=None, data_baixa=None, ua=None):
        data = {
            "unidade_administrativa_origem": (ua or self.ua).id,
            "itens": itens if itens is not None else [{"bem": self.bem.id}],
        }
        if data_baixa is not None:
            data["data_baixa"] = data_baixa
        else:
            data["data_baixa"] = str(timezone.localdate())
        return data

    def _serializer(self, data):
        return BaixaFisicaBemPatrimonialCreateSerializer(
            data=data,
            context={"request": self._req()},
        )

    def test_criacao_valida(self):
        s = self._serializer(self._data())
        self.assertTrue(s.is_valid(), s.errors)

    def test_sem_itens_invalido(self):
        s = self._serializer(self._data(itens=[]))
        self.assertFalse(s.is_valid())
        self.assertIn("itens", s.errors)

    def test_data_baixa_futura_invalida(self):
        from datetime import timedelta

        futura = str((timezone.localdate() + timedelta(days=1)))
        s = self._serializer(self._data(data_baixa=futura))
        self.assertFalse(s.is_valid())
        self.assertIn("data_baixa", s.errors)

    def test_numero_processo_bloqueado_na_criacao(self):
        s = self._serializer({**self._data(), "numero_processo_baixa": "6016.2025/0117371-7"})
        self.assertFalse(s.is_valid())
        self.assertIn("numero_processo_baixa", s.errors)

    def test_ua_inativa_invalida(self):
        from dados_comuns.models import UnidadeAdministrativa
        self.ua.status = UnidadeAdministrativa.INATIVA
        self.ua.save()
        s = self._serializer(self._data())
        self.assertFalse(s.is_valid())
        self.assertIn("unidade_administrativa_origem", s.errors)

    def test_create_cria_baixa_e_itens(self):
        s = self._serializer(self._data())
        self.assertTrue(s.is_valid(), s.errors)
        baixa = s.save()
        self.assertIsNotNone(baixa.id)
        self.assertEqual(baixa.status, constants.AGUARDANDO_ENVIO)
        self.assertEqual(baixa.criado_por, self.operador)
        self.assertEqual(baixa.itens.count(), 1)

    def test_create_atualiza_status_bem(self):
        s = self._serializer(self._data())
        s.is_valid(raise_exception=True)
        s.save()
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)


# ============================================================================
# TESTES DE SERIALIZER DE ATUALIZAÇÃO
# ============================================================================

class BaixaFisicaBemPatrimonialUpdateSerializerTestCase(BaseSetup):
    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)
        self.bem.status = constants.BAIXA_FISICA_AGUARDANDO_APROVACAO
        self.bem.save()

    def _serializer(self, data):
        return BaixaFisicaBemPatrimonialUpdateSerializer(
            instance=self.baixa,
            data=data,
            partial=True,
        )

    def test_edicao_valida(self):
        s = self._serializer({"itens": [{"bem": self.bem.id}]})
        self.assertTrue(s.is_valid(), s.errors)

    def test_sem_itens_invalido(self):
        s = self._serializer({"itens": []})
        self.assertFalse(s.is_valid())
        self.assertIn("itens", s.errors)

    def test_status_diferente_aguardando_envio_invalido(self):
        self.baixa.status = constants.SOLICITADA
        self.baixa.save()
        s = self._serializer({"itens": [{"bem": self.bem.id}]})
        self.assertFalse(s.is_valid())

    def test_update_troca_bem_atualiza_status(self):
        self.bem2.status = constants.APROVADO
        self.bem2.save()

        s = self._serializer({"itens": [{"bem": self.bem2.id}]})
        self.assertTrue(s.is_valid(), s.errors)
        s.save()

        self.bem.refresh_from_db()
        self.bem2.refresh_from_db()
        self.assertEqual(self.bem.status, constants.APROVADO)
        self.assertEqual(self.bem2.status, constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)

    def test_update_remove_item_nao_enviado(self):
        self.bem2.status = constants.APROVADO
        self.bem2.save()

        s = self._serializer({"itens": [{"bem": self.bem2.id}]})
        s.is_valid(raise_exception=True)
        s.save()

        self.assertEqual(self.baixa.itens.count(), 1)
        self.assertEqual(self.baixa.itens.first().bem, self.bem2)


# ============================================================================
# TESTES DE SERIALIZERS DE AÇÕES
# ============================================================================

class BaixaFisicaEnviarSolicitacaoSerializerTestCase(BaseSetup):
    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)

    def test_valido_quando_aguardando_envio(self):
        s = BaixaFisicaEnviarSolicitacaoSerializer(
            data={}, context={"baixa": self.baixa}
        )
        self.assertTrue(s.is_valid(), s.errors)

    def test_invalido_quando_status_diferente(self):
        self.baixa.status = constants.SOLICITADA
        self.baixa.save()
        s = BaixaFisicaEnviarSolicitacaoSerializer(
            data={}, context={"baixa": self.baixa}
        )
        self.assertFalse(s.is_valid())

    def test_invalido_sem_itens(self):
        baixa_vazia = criar_baixa(self.ua, self.operador, numero_processo_baixa="PROC-999")
        s = BaixaFisicaEnviarSolicitacaoSerializer(
            data={}, context={"baixa": baixa_vazia}
        )
        self.assertFalse(s.is_valid())


class BaixaFisicaAprovarSerializerTestCase(BaseSetup):
    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador, status=constants.SOLICITADA)

    def _req(self, user):
        req = MagicMock()
        req.user = user
        return req

    def _ctx(self, user):
        return {"baixa": self.baixa, "request": self._req(user)}

    def test_gestor_pode_aprovar(self):
        s = BaixaFisicaAprovarSerializer(
            data={"numero_processo_baixa": "6016.2025/0117371-7"},
            context=self._ctx(self.gestor),
        )
        self.assertTrue(s.is_valid(), s.errors)

    def test_operador_nao_pode_aprovar(self):
        s = BaixaFisicaAprovarSerializer(
            data={"numero_processo_baixa": "6016.2025/0117371-7"},
            context=self._ctx(self.operador),
        )
        with self.assertRaises(PermissionDenied):
            s.is_valid(raise_exception=True)

    def test_invalido_quando_status_diferente_de_solicitada(self):
        self.baixa.status = constants.AGUARDANDO_ENVIO
        self.baixa.save()
        s = BaixaFisicaAprovarSerializer(
            data={"numero_processo_baixa": "6016.2025/0117371-7"},
            context=self._ctx(self.gestor),
        )
        self.assertFalse(s.is_valid())


class BaixaFisicaCancelarSerializerTestCase(BaseSetup):
    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador)

    def _req(self, user):
        req = MagicMock()
        req.user = user
        return req

    def _ctx(self, user):
        return {"baixa": self.baixa, "request": self._req(user)}

    def test_gestor_pode_cancelar(self):
        s = BaixaFisicaCancelarSerializer(data={}, context=self._ctx(self.gestor))
        self.assertTrue(s.is_valid(), s.errors)

    def test_operador_nao_pode_cancelar(self):
        s = BaixaFisicaCancelarSerializer(data={}, context=self._ctx(self.operador))
        with self.assertRaises(PermissionDenied):
            s.is_valid(raise_exception=True)

    def test_nao_pode_cancelar_baixa_aceita(self):
        self.baixa.status = constants.ACEITA
        self.baixa.save()
        s = BaixaFisicaCancelarSerializer(data={}, context=self._ctx(self.gestor))
        self.assertFalse(s.is_valid())

    def test_motivo_opcional(self):
        s = BaixaFisicaCancelarSerializer(
            data={"motivo": "Motivo de teste"},
            context=self._ctx(self.gestor),
        )
        self.assertTrue(s.is_valid(), s.errors)

    def test_sem_motivo_valido(self):
        s = BaixaFisicaCancelarSerializer(data={"motivo": ""}, context=self._ctx(self.gestor))
        self.assertTrue(s.is_valid(), s.errors)


class BaixaFisicaSolicitarCorrecaoSerializerTestCase(BaseSetup):
    """
    Cobertura do novo BaixaFisicaSolicitarCorrecaoSerializer.

    Segue o mesmo padrão de BaixaFisicaCancelarSerializerTestCase, com as
    diferenças de regra de negócio do novo fluxo:
      - só é válido a partir do status "solicitada" (não "aguardando_envio")
      - motivo é OBRIGATÓRIO (cancelar tem motivo opcional)
    """

    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador, status=constants.SOLICITADA)

    def _req(self, user):
        req = MagicMock()
        req.user = user
        return req

    def _ctx(self, user):
        return {"baixa": self.baixa, "request": self._req(user)}

    def test_gestor_pode_solicitar_correcao(self):
        s = BaixaFisicaSolicitarCorrecaoSerializer(
            data={"motivo": "Corrigir o item X"},
            context=self._ctx(self.gestor),
        )
        self.assertTrue(s.is_valid(), s.errors)

    def test_operador_criador_pode_solicitar_correcao(self):
        # Operador criador da baixa pode devolver para correção
        s = BaixaFisicaSolicitarCorrecaoSerializer(
            data={"motivo": "Corrigir o item X"},
            context=self._ctx(self.operador),
        )
        self.assertTrue(s.is_valid(), s.errors)

    def test_operador_nao_criador_nao_pode_solicitar_correcao(self):
        # Operador que não é criador nem gestor não pode
        baixa_outra_ua = criar_baixa(self.ua2, self.operador2, status=constants.SOLICITADA)
        s = BaixaFisicaSolicitarCorrecaoSerializer(
            data={"motivo": "Corrigir o item X"},
            context={"baixa": baixa_outra_ua, "request": self._req(self.operador)},
        )
        with self.assertRaises(PermissionDenied):
            s.is_valid(raise_exception=True)

    def test_invalido_quando_status_diferente_de_solicitada(self):
        self.baixa.status = constants.AGUARDANDO_ENVIO
        self.baixa.save()
        s = BaixaFisicaSolicitarCorrecaoSerializer(
            data={"motivo": "Corrigir o item X"},
            context=self._ctx(self.gestor),
        )
        self.assertFalse(s.is_valid())

    def test_invalido_quando_baixa_ja_aceita(self):
        self.baixa.status = constants.ACEITA
        self.baixa.save()
        s = BaixaFisicaSolicitarCorrecaoSerializer(
            data={"motivo": "Corrigir o item X"},
            context=self._ctx(self.gestor),
        )
        self.assertFalse(s.is_valid())

    def test_motivo_obrigatorio_ausente_invalido(self):
        s = BaixaFisicaSolicitarCorrecaoSerializer(data={}, context=self._ctx(self.gestor))
        self.assertFalse(s.is_valid())
        self.assertIn("motivo", s.errors)

    def test_motivo_vazio_invalido(self):
        s = BaixaFisicaSolicitarCorrecaoSerializer(
            data={"motivo": ""},
            context=self._ctx(self.gestor),
        )
        self.assertFalse(s.is_valid())
        self.assertIn("motivo", s.errors)

    def test_motivo_apenas_espacos_invalido(self):
        s = BaixaFisicaSolicitarCorrecaoSerializer(
            data={"motivo": "   "},
            context=self._ctx(self.gestor),
        )
        self.assertFalse(s.is_valid())
        self.assertIn("motivo", s.errors)

    def test_motivo_e_normalizado_com_strip(self):
        s = BaixaFisicaSolicitarCorrecaoSerializer(
            data={"motivo": "  Corrigir o item X  "},
            context=self._ctx(self.gestor),
        )
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data["motivo"], "Corrigir o item X")


# ============================================================================
# TESTES DO SERIALIZER DE DETALHE (URLs de ação)
# ============================================================================

class BaixaFisicaDetailSerializerUrlsTestCase(BaseSetup):
    def _serializer(self, baixa, user):
        req = MagicMock()
        req.user = user
        req.build_absolute_uri = lambda path: f"https://testserver{path}"
        return BaixaFisicaBemPatrimonialDetailSerializer(
            baixa, context={"request": req}
        )

    def test_url_solicitar_quando_aguardando_envio(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.AGUARDANDO_ENVIO)
        data = self._serializer(baixa, self.operador).data
        self.assertIsNotNone(data["url_solicitar"])

    def test_url_aprovar_quando_solicitada(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.SOLICITADA)
        data = self._serializer(baixa, self.gestor).data
        self.assertIsNotNone(data["url_aprovar"])
        self.assertIsNone(data["url_solicitar"])

    def test_url_cancelar_disponivel_para_aguardando_e_solicitada(self):
        for st in [constants.AGUARDANDO_ENVIO, constants.SOLICITADA]:
            baixa = criar_baixa(self.ua, self.operador, status=st,
                                numero_processo_baixa=f"PROC-{st}")
            data = self._serializer(baixa, self.gestor).data
            self.assertIsNotNone(data["url_recusar"], f"Esperava url_recusar para status={st}")

    def test_url_cancelar_indisponivel_quando_aceita(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        data = self._serializer(baixa, self.gestor).data
        self.assertIsNone(data["url_recusar"])

    def test_url_gerar_nbbpm_quando_aceita_com_nbbpm(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        # Cria NBBPM consolidada vinculada (nova tabela M2M) - legado numero_nbbpm desativado
        nbbpm = NBBPM.objects.create(
            numero="016.0000001.2026",
            numero_processo_baixa="PROC-URL",
            data_autorizacao=timezone.localdate(),
            responsavel="Gestor",
            criado_por=self.gestor,
        )
        nbbpm.baixas.set([baixa])
        data = self._serializer(baixa, self.gestor).data
        self.assertIsNotNone(data["url_gerar_nbbpm"])

    def test_url_gerar_nbbpm_ausente_sem_numero(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        data = self._serializer(baixa, self.gestor).data
        self.assertIsNone(data["url_gerar_nbbpm"])

    def test_url_solicitar_correcao_quando_solicitada_e_gestor(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.SOLICITADA)
        data = self._serializer(baixa, self.gestor).data
        self.assertIsNotNone(data["url_solicitar_correcao"])

    def test_url_solicitar_correcao_para_operador_criador_quando_solicitada(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.SOLICITADA)
        data = self._serializer(baixa, self.operador).data
        self.assertIsNotNone(data["url_solicitar_correcao"])

    def test_url_solicitar_correcao_ausente_para_operador_nao_criador(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.SOLICITADA)
        data = self._serializer(baixa, self.operador2).data
        self.assertIsNone(data["url_solicitar_correcao"])

    def test_url_solicitar_correcao_ausente_quando_aguardando_envio(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.AGUARDANDO_ENVIO)
        data = self._serializer(baixa, self.gestor).data
        self.assertIsNone(data["url_solicitar_correcao"])

    def test_url_solicitar_correcao_ausente_quando_aceita(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        data = self._serializer(baixa, self.gestor).data
        self.assertIsNone(data["url_solicitar_correcao"])


# ============================================================================
# TESTES DO VIEWSET — AUTENTICAÇÃO E PERMISSÕES
# ============================================================================

class BaixaFisicaViewSetPermissaoTestCase(BaseAPISetup):
    def test_anonimo_recebe_401(self):
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_usuario_sem_grupo_recebe_403(self):
        sem_grupo = criar_usuario("sem_grupo", self.uo, self.ua)
        self._auth(sem_grupo)
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_operador_pode_listar(self):
        self._auth(self.operador)
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_gestor_pode_listar(self):
        self._auth(self.gestor)
        resp = self.client.get(self.list_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ============================================================================
# TESTES DO VIEWSET — LIST
# ============================================================================

class BaixaFisicaViewSetListTestCase(BaseAPISetup):
    def setUp(self):
        super().setUp()
        self.baixa1 = criar_baixa(self.ua, self.operador,
                                  numero_processo_baixa="PROC-001")
        self.baixa2 = criar_baixa(self.ua2, self.operador2,
                                  numero_processo_baixa="PROC-002")

    def test_operador_ve_apenas_sua_ua(self):
        self._auth(self.operador)
        resp = self.client.get(self.list_url)
        ids = [r["id"] for r in resp.data["results"]]
        self.assertIn(self.baixa1.id, ids)
        self.assertNotIn(self.baixa2.id, ids)

    def test_gestor_ve_todas(self):
        self.gestor.unidade_administrativa = None
        self.gestor.save()
        self._auth(self.gestor)
        resp = self.client.get(self.list_url)
        ids = [r["id"] for r in resp.data["results"]]
        self.assertIn(self.baixa1.id, ids)
        self.assertIn(self.baixa2.id, ids)

    def test_filtro_por_status(self):
        criar_baixa(self.ua, self.operador, status=constants.SOLICITADA,
                    numero_processo_baixa="PROC-SOL")
        self._auth(self.operador)
        resp = self.client.get(self.list_url, {"status": constants.AGUARDANDO_ENVIO})
        for item in resp.data["results"]:
            self.assertEqual(item["status"], constants.AGUARDANDO_ENVIO)

    def test_busca_por_numero_processo(self):
        self._auth(self.operador)
        resp = self.client.get(self.list_url, {"search": "PROC-001"})
        ids = [r["id"] for r in resp.data["results"]]
        self.assertIn(self.baixa1.id, ids)

    def test_ordenacao_por_data_criacao_desc(self):
        self._auth(self.operador)
        resp = self.client.get(self.list_url, {"ordering": "-data_criacao"})
        results = resp.data["results"]
        if len(results) > 1:
            self.assertGreaterEqual(results[0]["id"], results[-1]["id"])

    def test_paginacao_presente(self):
        self._auth(self.operador)
        resp = self.client.get(self.list_url)
        self.assertIn("results", resp.data)
        self.assertIn("count", resp.data)


# ============================================================================
# TESTES DO VIEWSET — CREATE
# ============================================================================

class BaixaFisicaViewSetCreateTestCase(BaseAPISetup):
    def _payload(self, **kwargs):
        payload = {
            "unidade_administrativa_origem": self.ua.id,
            "itens": [{"bem": self.bem.id}],
            **kwargs,
        }
        if "data_baixa" not in kwargs:
            payload["data_baixa"] = str(timezone.localdate())
        return payload

    def test_criacao_sem_itens_retorna_400(self):
        self._auth(self.operador)
        resp = self.client.post(self.list_url, self._payload(itens=[]), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_criacao_sem_ua_retorna_400(self):
        self._auth(self.operador)
        payload = self._payload()
        payload.pop("unidade_administrativa_origem")
        resp = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_criacao_com_data_futura_retorna_400(self):
        from datetime import timedelta
        self._auth(self.operador)
        futura = str(timezone.localdate() + timedelta(days=2))
        resp = self.client.post(self.list_url, self._payload(data_baixa=futura), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_criacao_com_processo_retorna_400(self):
        self._auth(self.operador)
        resp = self.client.post(
            self.list_url, self._payload(numero_processo_baixa="6016.2025/0117371-7"), format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_criacao_atualiza_status_bem(self):
        self._auth(self.operador)
        self.client.post(self.list_url, self._payload(), format="json")
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)


# ============================================================================
# TESTES DO VIEWSET — RETRIEVE
# ============================================================================

class BaixaFisicaViewSetRetrieveTestCase(BaseAPISetup):
    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)

    def test_retrieve_retorna_dados_completos(self):
        self._auth(self.operador)
        resp = self.client.get(self.detail_url(self.baixa.id))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("itens", resp.data)
        self.assertEqual(len(resp.data["itens"]), 1)

    def test_retrieve_inexistente_retorna_404(self):
        self._auth(self.operador)
        resp = self.client.get(self.detail_url(99999))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_outra_ua_retorna_404(self):
        self._auth(self.operador2)
        resp = self.client.get(self.detail_url(self.baixa.id))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ============================================================================
# TESTES DO VIEWSET — UPDATE
# ============================================================================

class BaixaFisicaViewSetUpdateTestCase(BaseAPISetup):
    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)
        self.bem.status = constants.BAIXA_FISICA_AGUARDANDO_APROVACAO
        self.bem.save()

    def test_patch_numero_processo_retorna_400(self):
        self._auth(self.operador)
        resp = self.client.patch(
            self.detail_url(self.baixa.id),
            {"numero_processo_baixa": "PROC-ALTERADO",
             "itens": [{"bem": self.bem.id}]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.numero_processo_baixa, "PROC-BX-001")

    def test_update_quando_solicitada_retorna_400(self):
        self.baixa.status = constants.SOLICITADA
        self.baixa.save()
        self._auth(self.operador)
        resp = self.client.patch(
            self.detail_url(self.baixa.id),
            {"itens": [{"bem": self.bem.id}]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_troca_bem(self):
        self.bem2.status = constants.APROVADO
        self.bem2.save()
        self._auth(self.operador)
        resp = self.client.patch(
            self.detail_url(self.baixa.id),
            {"itens": [{"bem": self.bem2.id}]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.bem.refresh_from_db()
        self.bem2.refresh_from_db()
        self.assertEqual(self.bem.status, constants.APROVADO)
        self.assertEqual(self.bem2.status, constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)

    def test_update_retorna_itens_persistidos(self):
        self.bem2.status = constants.APROVADO
        self.bem2.save()
        novo_bem = criar_bem(
            self.ua,
            self.operador,
            numero_patrimonial="000.000000003-0",
        )
        self._auth(self.operador)
        resp = self.client.patch(
            self.detail_url(self.baixa.id),
            {"itens": [{"bem": self.bem2.id}, {"bem": novo_bem.id}]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["bem"]["id"] for item in resp.data["itens"]],
            [self.bem2.id, novo_bem.id],
        )


# ============================================================================
# TESTES DO VIEWSET — ENVIAR SOLICITAÇÃO
# ============================================================================

class BaixaFisicaViewSetEnviarSolicitacaoTestCase(BaseAPISetup):
    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_solicitada")
    def test_enviar_solicitacao_com_sucesso(self, mock_email):
        self._auth(self.operador)
        resp = self.client.post(self.action_url(self.baixa.id, "enviar-solicitacao"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, constants.SOLICITADA)

    def test_enviar_solicitacao_sem_itens_retorna_400(self):
        self.baixa.itens.all().delete()
        self._auth(self.operador)
        resp = self.client.post(self.action_url(self.baixa.id, "enviar-solicitacao"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_aprovada")
    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_solicitada")
    def test_enviar_solicitacao_nao_reabre_baixa_aceita(self, mock_email_solicitada, mock_email_aprovada):
        self._auth(self.operador)
        self.client.post(self.action_url(self.baixa.id, "enviar-solicitacao"))
        self._auth(self.gestor)
        self.client.post(
            self.action_url(self.baixa.id, "aprovar"),
            {"numero_processo_baixa": "6016.2025/0117371-7"},
            format="json",
        )
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, constants.ACEITA)

        self._auth(self.operador)
        resp = self.client.post(self.action_url(self.baixa.id, "enviar-solicitacao"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, constants.ACEITA)


# ============================================================================
# TESTES DO VIEWSET — HISTÓRICO
# ============================================================================

class BaixaFisicaViewSetHistoricoTestCase(BaseAPISetup):
    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)

    def test_historico_retorna_data_alteracao(self):
        self._auth(self.operador)
        self.client.post(self.action_url(self.baixa.id, "enviar-solicitacao"))
        resp = self.client.get(self.action_url(self.baixa.id, "historico"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data)
        self.assertIsNotNone(resp.data[0]["data_alteracao"])

# ============================================================================
# TESTES DO VIEWSET — APROVAR
# ============================================================================


class BaixaFisicaViewSetAprovarTestCase(BaseAPISetup):
    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador, status=constants.SOLICITADA)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_aprovada")
    def test_gestor_aprova(self, mock_email):
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "aprovar"),
            {"numero_processo_baixa": "6016.2025/0117371-7"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, constants.ACEITA)
        self.assertEqual(self.baixa.aprovado_por, self.gestor)
        self.assertIsNotNone(self.baixa.data_aprovacao)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_aprovada")
    def test_aprovacao_nao_gera_nbbpm(self, mock_email):
        # NBBPM somente via tela de NBBPM (lote)
        self._auth(self.gestor)
        self.client.post(
            self.action_url(self.baixa.id, "aprovar"),
            {"numero_processo_baixa": "6016.2025/0117371-7"},
            format="json",
        )
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, constants.ACEITA)
        self.assertEqual((self.baixa.numero_nbbpm or "").strip(), "")
        self.assertFalse(self.baixa.nbbpms_lote.exists())
        self.assertFalse(NBBPM.objects.exists())

    def test_operador_nao_pode_aprovar(self):
        self._auth(self.operador)
        resp = self.client.post(
            self.action_url(self.baixa.id, "aprovar"),
            {"numero_processo_baixa": "6016.2025/0117371-7"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_aprovar_status_errado_retorna_400(self):
        self.baixa.status = constants.AGUARDANDO_ENVIO
        self.baixa.save()
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "aprovar"),
            {"numero_processo_baixa": "6016.2025/0117371-7"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_aprovada",
           side_effect=Exception("Erro de email"))
    def test_falha_email_nao_impede_aprovacao(self, mock_email):
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "aprovar"),
            {"numero_processo_baixa": "6016.2025/0117371-7"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ============================================================================
# TESTES DO VIEWSET — CANCELAR
# ============================================================================

class BaixaFisicaViewSetCancelarTestCase(BaseAPISetup):
    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)
        self.bem.status = constants.BAIXA_FISICA_AGUARDANDO_APROVACAO
        self.bem.save()

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_cancelada")
    def test_gestor_cancela_baixa(self, mock_email):
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "recusar"),
            {"motivo": "Cancelamento de teste"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, constants.RECUSADA)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_cancelada")
    def test_cancelamento_restaura_status_bem(self, mock_email):
        self._auth(self.gestor)
        self.client.post(
            self.action_url(self.baixa.id, "recusar"), {}, format="json"
        )
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, constants.APROVADO)

    def test_operador_nao_pode_cancelar(self):
        self._auth(self.operador)
        resp = self.client.post(
            self.action_url(self.baixa.id, "recusar"), {}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_nao_pode_cancelar_baixa_aceita(self):
        self.baixa.status = constants.ACEITA
        self.baixa.save()
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "recusar"), {}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_cancelada",
           side_effect=Exception("Erro email"))
    def test_falha_email_nao_impede_cancelamento(self, mock_email):
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "recusar"), {"motivo": "Cancelamento de teste"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_cancelada")
    def test_cancelamento_sem_motivo_valido(self, mock_email):
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "recusar"), {}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ============================================================================
# TESTES DO VIEWSET — SOLICITAR CORREÇÃO
# ============================================================================

class BaixaFisicaViewSetSolicitarCorrecaoTestCase(BaseAPISetup):
    """
    Cobertura do novo endpoint POST /baixa-fisica/{id}/solicitar-correcao/.

    Segue o mesmo padrão de BaixaFisicaViewSetCancelarTestCase, mas:
      - parte de uma baixa "solicitada" (não "aguardando_envio")
      - motivo é obrigatório (400 sem ele)
      - status final esperado é AGUARDANDO_ENVIO (não RECUSADA)
      - os bens NÃO são restaurados para APROVADO (a baixa continua em
        andamento, apenas voltando para edição)
    """

    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador, status=constants.SOLICITADA)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)
        self.bem.status = constants.BAIXA_FISICA_AGUARDANDO_APROVACAO
        self.bem.save()

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_cancelada")
    def test_gestor_solicita_correcao(self, mock_email):
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "solicitar-correcao"),
            {"motivo": "Corrigir o item com número patrimonial X"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, constants.AGUARDANDO_ENVIO)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_cancelada")
    def test_solicitar_correcao_nao_restaura_status_bem(self, mock_email):
        self._auth(self.gestor)
        self.client.post(
            self.action_url(self.baixa.id, "solicitar-correcao"),
            {"motivo": "Corrigir o item"},
            format="json",
        )
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)

    def test_solicitar_correcao_sem_motivo_retorna_400(self):
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "solicitar-correcao"), {}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, constants.SOLICITADA)

    def test_solicitar_correcao_motivo_vazio_retorna_400(self):
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "solicitar-correcao"),
            {"motivo": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_operador_criador_pode_solicitar_correcao(self):
        self._auth(self.operador)
        resp = self.client.post(
            self.action_url(self.baixa.id, "solicitar-correcao"),
            {"motivo": "Corrigir o item"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, constants.AGUARDANDO_ENVIO)

    def test_operador_nao_criador_nao_pode_solicitar_correcao(self):
        # baixa criada por operador, tenta solicitar correção com outro operador da mesma UA (não criador)
        from usuario.constants import GRUPO_OPERADOR_INVENTARIO
        operador_mesma_ua = criar_usuario("operador_mesma_ua_correcao", self.uo, self.ua, grupos=[GRUPO_OPERADOR_INVENTARIO])
        self._auth(operador_mesma_ua)
        resp = self.client.post(
            self.action_url(self.baixa.id, "solicitar-correcao"),
            {"motivo": "Corrigir o item"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, constants.SOLICITADA)

    def test_nao_pode_solicitar_correcao_de_baixa_aguardando_envio(self):
        self.baixa.status = constants.AGUARDANDO_ENVIO
        self.baixa.save()
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "solicitar-correcao"),
            {"motivo": "Corrigir o item"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nao_pode_solicitar_correcao_de_baixa_aceita(self):
        self.baixa.status = constants.ACEITA
        self.baixa.save()
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "solicitar-correcao"),
            {"motivo": "Corrigir o item"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_cancelada",
           side_effect=Exception("Erro email"))
    def test_falha_email_nao_impede_solicitacao_de_correcao(self, mock_email):
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "solicitar-correcao"),
            {"motivo": "Corrigir o item"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_cancelada")
    def test_solicitar_correcao_registra_historico_com_motivo(self, mock_email):
        self._auth(self.gestor)
        motivo = "Corrigir o item com número patrimonial 001.053500289-0"
        self.client.post(
            self.action_url(self.baixa.id, "solicitar-correcao"),
            {"motivo": motivo},
            format="json",
        )
        resp = self.client.get(self.action_url(self.baixa.id, "historico"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        justificativas = [item.get("justificativa", "") for item in resp.data]
        self.assertTrue(any(motivo in (j or "") for j in justificativas))

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_cancelada")
    def test_baixa_pode_ser_reenviada_apos_solicitar_correcao(self, mock_email):
        self._auth(self.gestor)
        self.client.post(
            self.action_url(self.baixa.id, "solicitar-correcao"),
            {"motivo": "Corrigir o item"},
            format="json",
        )
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, constants.AGUARDANDO_ENVIO)

        self._auth(self.operador)
        resp = self.client.post(self.action_url(self.baixa.id, "enviar-solicitacao"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, constants.SOLICITADA)


# ============================================================================
# TESTES DO VIEWSET — EXPORTAR EXCEL
# ============================================================================

class BaixaFisicaViewSetExportarExcelTestCase(BaseAPISetup):
    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)

    def test_exportar_excel_retorna_xlsx(self):
        self._auth(self.operador)
        resp = self.client.get(
            reverse("baixas-fisicas-exportar-excel")
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(
            resp["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_exportar_excel_respeita_escopo(self):
        self._auth(self.operador)
        resp = self.client.get(
            reverse("baixas-fisicas-exportar-excel")
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_exportar_excel_filtro_por_ids(self):
        self._auth(self.operador)
        resp = self.client.get(
            reverse("baixas-fisicas-exportar-excel"),
            {"ids": str(self.baixa.id)},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_exportar_excel_ids_invalidos_ignorados(self):
        self._auth(self.operador)
        resp = self.client.get(
            reverse("baixas-fisicas-exportar-excel"),
            {"ids": "abc,xyz"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_exportar_excel_sem_itens_inclui_linha(self):
        criar_baixa(self.ua, self.operador, numero_processo_baixa="PROC-VAZIO")
        self._auth(self.operador)
        resp = self.client.get(
            reverse("baixas-fisicas-exportar-excel")
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_nome_arquivo_no_header(self):
        self._auth(self.operador)
        resp = self.client.get(
            reverse("baixas-fisicas-exportar-excel")
        )
        self.assertIn("baixas_fisicas_", resp["Content-Disposition"])
        self.assertIn(".xlsx", resp["Content-Disposition"])


# ============================================================================
# TESTES DO VIEWSET — QUERYSET E ESCOPO
# ============================================================================

class BaixaFisicaViewSetQuerysetTestCase(BaseAPISetup):
    def setUp(self):
        super().setUp()
        self.baixa_ua1 = criar_baixa(self.ua, self.operador, numero_processo_baixa="P1")
        self.baixa_ua2 = criar_baixa(self.ua2, self.operador2, numero_processo_baixa="P2")

    def test_operador_ua1_ve_apenas_baixas_ua1(self):
        self._auth(self.operador)
        resp = self.client.get(self.list_url)
        ids = [r["id"] for r in resp.data["results"]]
        self.assertIn(self.baixa_ua1.id, ids)
        self.assertNotIn(self.baixa_ua2.id, ids)

    def test_gestor_sem_ua_ve_todas(self):
        self.gestor.unidade_administrativa = None
        self.gestor.save()
        self._auth(self.gestor)
        resp = self.client.get(self.list_url)
        ids = [r["id"] for r in resp.data["results"]]
        self.assertIn(self.baixa_ua1.id, ids)
        self.assertIn(self.baixa_ua2.id, ids)

    def test_serializer_list_retorna_campos_corretos(self):
        self._auth(self.operador)
        resp = self.client.get(self.list_url)
        if resp.data["results"]:
            item = resp.data["results"][0]
            for campo in ["id", "status", "status_display", "total_itens",
                          "data_criacao", "numero_processo_baixa"]:
                self.assertIn(campo, item)

    def test_total_itens_no_list(self):
        BaixaFisicaBensItem.objects.create(
            baixa=self.baixa_ua1, bem=self.bem
        )
        self._auth(self.operador)
        resp = self.client.get(self.list_url)
        item = next(r for r in resp.data["results"] if r["id"] == self.baixa_ua1.id)
        self.assertEqual(item["total_itens"], 1)


# ============================================================================
# TESTES DE SERIALIZER — NBBPMGerarLoteSerializer
# ============================================================================

class NBBPMGerarLoteSerializerTestCase(BaseSetup):
    def setUp(self):
        super().setUp()
        self.baixa1 = criar_baixa(
            self.ua, self.operador, status=constants.ACEITA,
            numero_processo_baixa="6016.2025/0117371-7",
        )
        self.baixa2 = criar_baixa(
            self.ua, self.operador, status=constants.ACEITA,
            numero_processo_baixa="6016.2025/0117371-7",
        )

    def _req(self, user):
        req = MagicMock()
        req.user = user
        return req

    def _data(self, **overrides):
        data = {
            "baixas": [self.baixa1.id, self.baixa2.id],
            "numero_processo_baixa": "6016.2025/0117371-7",
            "data_autorizacao": str(timezone.localdate()),
            "responsavel": "Responsavel Teste",
        }
        data.update(overrides)
        return data

    def _serializer(self, data, user=None):
        return NBBPMGerarLoteSerializer(
            data=data,
            context={"request": self._req(user or self.gestor)},
        )

    def test_dados_validos(self):
        s = self._serializer(self._data())
        self.assertTrue(s.is_valid(), s.errors)

    def test_strip_no_numero_processo_baixa(self):
        s = self._serializer(self._data(numero_processo_baixa="  6016.2025/0117371-7  "))
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(
            s.validated_data["numero_processo_baixa"], "6016.2025/0117371-7"
        )

    def test_strip_no_responsavel(self):
        s = self._serializer(self._data(responsavel="  Responsavel Teste  "))
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data["responsavel"], "Responsavel Teste")

    def test_strip_no_numero_processo_destinacao_final(self):
        s = self._serializer(
            self._data(numero_processo_destinacao_final="  6016.2025/9999999-9  ")
        )
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(
            s.validated_data["numero_processo_destinacao_final"],
            "6016.2025/9999999-9",
        )

    def test_numero_processo_destinacao_final_default_vazio(self):
        s = self._serializer(self._data())
        self.assertTrue(s.is_valid(), s.errors)
        self.assertEqual(s.validated_data["numero_processo_destinacao_final"], "")

    def test_lista_de_baixas_vazia_invalida(self):
        s = self._serializer(self._data(baixas=[]))
        self.assertFalse(s.is_valid())
        self.assertIn("baixas", s.errors)

    def test_baixa_fora_do_escopo_invalida(self):
        baixa_ua2 = criar_baixa(
            self.ua2, self.operador2, status=constants.ACEITA,
            numero_processo_baixa="6016.2025/0117371-7",
        )
        s = self._serializer(
            self._data(baixas=[self.baixa1.id, baixa_ua2.id]), user=self.gestor
        )
        self.assertFalse(s.is_valid())
        self.assertIn("baixas", s.errors)

    def test_baixa_status_diferente_de_aceita_invalida(self):
        self.baixa1.status = constants.AGUARDANDO_ENVIO
        self.baixa1.save()
        s = self._serializer(self._data())
        self.assertFalse(s.is_valid())
        self.assertIn("baixas", s.errors)

    @patch("bem_patrimonial.api_serializers.filtrar_queryset_por_escopo")
    def test_baixas_de_unidades_orcamentarias_diferentes_invalida(self, mock_escopo):
        # Isolado do pré-filtro de escopo — regra agora é mesma UO com prefixo fixo 001
        uo2 = criar_uo(codigo="200", nome="UO Dois", sigla="UOD")
        ua3 = criar_ua(uo=uo2, codigo="003", nome="UA Três", sigla="UAT2")
        operador3 = criar_usuario(
            "operador3_serializer", uo2, ua3, grupos=[GRUPO_OPERADOR_INVENTARIO]
        )
        baixa_uo2 = criar_baixa(
            ua3, operador3, status=constants.ACEITA, numero_processo_baixa="6016.2025/0117371-7"
        )

        mock_escopo.return_value = BaixaFisicaBemPatrimonial.objects.all()

        self.gestor.unidade_administrativa = None
        self.gestor.save()

        s = self._serializer(
            self._data(baixas=[self.baixa1.id, baixa_uo2.id]), user=self.gestor
        )
        self.assertFalse(s.is_valid())
        self.assertIn("Unidade Orçamentária", str(s.errors["baixas"]))

    def test_baixa_ja_utilizada_em_nbbpm_invalida(self):
        nbbpm = NBBPM.objects.create(
            numero="001.0000001.2026",
            numero_processo_baixa="PROC-EXISTENTE",
            data_autorizacao=timezone.localdate(),
            responsavel="Responsável Anterior",
            criado_por=self.operador,
        )
        nbbpm.baixas.set([self.baixa1])

        s = self._serializer(self._data())
        self.assertFalse(s.is_valid())
        self.assertIn("baixas", s.errors)

    def test_create_persiste_nbbpm_com_baixas_e_criado_por(self):
        s = self._serializer(self._data())
        self.assertTrue(s.is_valid(), s.errors)
        nbbpm = s.save()

        self.assertIsInstance(nbbpm, NBBPM)
        self.assertEqual(nbbpm.criado_por, self.gestor)
        self.assertEqual(
            set(nbbpm.baixas.values_list("id", flat=True)),
            {self.baixa1.id, self.baixa2.id},
        )
        # serializer já gera número via serviço unificado (prefixo fixo 001)
        self.assertRegex(nbbpm.numero, r"^\d{3}\.\d{7}[\./]\d{4}$")


class NBBPMProcessoUnicoTestCase(BaseAPISetup):
    """NBBPM só gera com Baixas do mesmo processo; payload deve ser igual."""

    PROCESSO = "6016.2025/0117371-7"

    def setUp(self):
        super().setUp()
        self.baixa1 = criar_baixa(
            self.ua, self.operador, status=constants.ACEITA,
            numero_processo_baixa=self.PROCESSO,
        )
        self.baixa2 = criar_baixa(
            self.ua, self.operador, status=constants.ACEITA,
            numero_processo_baixa=self.PROCESSO,
        )
        self.baixa_outro_processo = criar_baixa(
            self.ua, self.operador, status=constants.ACEITA,
            numero_processo_baixa="6016.2025/0999999-9",
        )

    def _req(self, user=None):
        req = MagicMock()
        req.user = user or self.gestor
        return req

    def _payload(self, baixas, numero=None, **overrides):
        data = {
            "baixas": [b.id for b in baixas],
            "numero_processo_baixa": numero if numero is not None else self.PROCESSO,
            "data_autorizacao": str(timezone.localdate()),
            "responsavel": "Responsavel Teste",
        }
        data.update(overrides)
        return data

    def test_serializer_bloqueia_processos_divergentes(self):
        s = NBBPMGerarLoteSerializer(
            data=self._payload([self.baixa1, self.baixa_outro_processo]),
            context={"request": self._req()},
        )
        self.assertFalse(s.is_valid())
        self.assertIn("baixas", s.errors)
        self.assertIn("divergentes", str(s.errors["baixas"]))

    def test_serializer_bloqueia_payload_divergente_das_baixas(self):
        s = NBBPMGerarLoteSerializer(
            data=self._payload([self.baixa1, self.baixa2], numero="6016.2025/0000000-0"),
            context={"request": self._req()},
        )
        self.assertFalse(s.is_valid())
        self.assertIn("numero_processo_baixa", s.errors)
        self.assertIn("diverge", str(s.errors["numero_processo_baixa"]))

    def test_serializer_ok_com_mesmo_processo_e_strip(self):
        s = NBBPMGerarLoteSerializer(
            data=self._payload([self.baixa1, self.baixa2], numero=f"  {self.PROCESSO}  "),
            context={"request": self._req()},
        )
        self.assertTrue(s.is_valid(), s.errors)

    def test_post_bloqueia_processos_divergentes(self):
        self._auth(self.gestor)
        resp = self.client.post("/api/nbbpm/", self._payload([self.baixa1, self.baixa_outro_processo]), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("divergentes", str(resp.data))

    def test_post_bloqueia_payload_divergente(self):
        self._auth(self.gestor)
        resp = self.client.post("/api/nbbpm/", self._payload([self.baixa1], numero="6016.2025/0000000-0"), format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("diverge", str(resp.data))

    def test_post_gera_201_com_mesmo_processo(self):
        self._auth(self.gestor)
        resp = self.client.post("/api/nbbpm/", self._payload([self.baixa1, self.baixa2]), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data["numero_processo_baixa"], self.PROCESSO)


# ============================================================================
# TESTES DE SERIALIZER — NBBPMSerializer
# ============================================================================

class NBBPMSerializerTestCase(BaseSetup):
    def setUp(self):
        super().setUp()
        self.baixa1 = criar_baixa(
            self.ua, self.operador, status=constants.ACEITA,
            numero_processo_baixa="P1",
        )
        self.nbbpm = NBBPM.objects.create(
            numero="001.0000001.2026",
            numero_processo_baixa="6016.2025/0117371-7",
            data_autorizacao=timezone.localdate(),
            responsavel="Responsavel Teste",
            numero_processo_destinacao_final="6016.2025/9999999-9",
            criado_por=self.operador,
        )
        self.nbbpm.baixas.set([self.baixa1])

    def test_campos_retornados(self):
        data = NBBPMSerializer(self.nbbpm).data
        for campo in [
            "id", "numero", "baixas", "unidade_administrativa_origem",
            "numero_processo_baixa", "data_autorizacao", "responsavel",
            "numero_processo_destinacao_final", "criado_por", "data_criacao",
        ]:
            self.assertIn(campo, data)

    def test_valores_corretos(self):
        data = NBBPMSerializer(self.nbbpm).data
        self.assertEqual(data["numero"], "001.0000001.2026")
        self.assertEqual(data["numero_processo_baixa"], "6016.2025/0117371-7")
        self.assertEqual(data["responsavel"], "Responsavel Teste")
        self.assertEqual(
            data["numero_processo_destinacao_final"], "6016.2025/9999999-9"
        )
        self.assertEqual(data["baixas"], [self.baixa1.id])

    def test_unidade_administrativa_origem_serializada(self):
        data = NBBPMSerializer(self.nbbpm).data
        self.assertEqual(data["unidade_administrativa_origem"]["id"], self.ua.id)
        self.assertEqual(data["unidade_administrativa_origem"]["sigla"], self.ua.sigla)

    def test_criado_por_serializado(self):
        data = NBBPMSerializer(self.nbbpm).data
        self.assertEqual(data["criado_por"]["username"], self.operador.username)

    def test_unidade_administrativa_origem_none_quando_sem_baixas(self):
        nbbpm_sem_baixas = NBBPM.objects.create(
            numero_processo_baixa="PROC-VAZIO",
            data_autorizacao=timezone.localdate(),
            responsavel="Responsável Teste",
            criado_por=self.operador,
        )
        data = NBBPMSerializer(nbbpm_sem_baixas).data
        self.assertIsNone(data["unidade_administrativa_origem"])


# ============================================================================
# TESTES — CORRIGIR NÚMERO DO PROCESSO (Baixa Aceita, sem Nota)
# ============================================================================

class BaixaFisicaCorrigirProcessoSerializerTestCase(BaseSetup):
    def setUp(self):
        super().setUp()
        from bem_patrimonial.api_serializers import BaixaFisicaCorrigirProcessoSerializer

        self.Serializer = BaixaFisicaCorrigirProcessoSerializer
        self.baixa = criar_baixa(
            self.ua, self.operador, status=constants.ACEITA,
            numero_processo_baixa="6016.2025/0117371-7",
        )

    def _req(self, user):
        req = MagicMock()
        req.user = user
        return req

    def test_valido_gestor_aceita_sem_nota(self):
        s = self.Serializer(
            data={"numero_processo_baixa": "6016.2025/0222222-2"},
            context={"baixa": self.baixa, "request": self._req(self.gestor)},
        )
        self.assertTrue(s.is_valid(), s.errors)

    def test_formato_invalido(self):
        s = self.Serializer(
            data={"numero_processo_baixa": "FORMATO-RUIM"},
            context={"baixa": self.baixa, "request": self._req(self.gestor)},
        )
        self.assertFalse(s.is_valid())
        self.assertIn("numero_processo_baixa", s.errors)

    def test_operador_sem_permissao(self):
        s = self.Serializer(
            data={"numero_processo_baixa": "6016.2025/0222222-2"},
            context={"baixa": self.baixa, "request": self._req(self.operador)},
        )
        with self.assertRaises(PermissionDenied):
            s.is_valid(raise_exception=True)

    def test_status_nao_aceita_invalido(self):
        self.baixa.status = constants.SOLICITADA
        self.baixa.save()
        s = self.Serializer(
            data={"numero_processo_baixa": "6016.2025/0222222-2"},
            context={"baixa": self.baixa, "request": self._req(self.gestor)},
        )
        self.assertFalse(s.is_valid())

    def test_com_nbbpm_vinculada_invalido(self):
        nbbpm = NBBPM.objects.create(
            numero="001.0000001/2026",
            numero_processo_baixa="6016.2025/0117371-7",
            data_autorizacao=timezone.localdate(),
            responsavel="G",
            criado_por=self.gestor,
        )
        nbbpm.baixas.set([self.baixa])
        s = self.Serializer(
            data={"numero_processo_baixa": "6016.2025/0222222-2"},
            context={"baixa": self.baixa, "request": self._req(self.gestor)},
        )
        self.assertFalse(s.is_valid())


class BaixaFisicaCorrigirProcessoViewSetTestCase(BaseAPISetup):
    PROCESSO_ANTIGO = "6016.2025/0117371-7"
    PROCESSO_NOVO = "6016.2025/0222222-2"

    def _nova_baixa_aceita(self, processo=None):
        baixa = criar_baixa(
            self.ua, self.operador, status=constants.ACEITA,
            numero_processo_baixa=processo or self.PROCESSO_ANTIGO,
        )
        baixa.aprovado_por = self.gestor
        baixa.data_aprovacao = timezone.now()
        baixa.save(update_fields=["aprovado_por", "data_aprovacao"])
        return baixa

    def _vincular_bem_baixado(self, baixa, bem):
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=bem)
        bem.status = constants.BAIXA_FISICA
        bem.numero_processo = baixa.numero_processo_baixa
        bem.localizacao = f"Baixa Física - {baixa.numero_processo_baixa}"
        bem.save(update_fields=["status", "numero_processo", "localizacao"])

    def _criar_baixa_aceita_com_bem(self, processo=None):
        baixa = self._nova_baixa_aceita(processo)
        self._vincular_bem_baixado(baixa, self.bem)
        return baixa

    def _contar_historico(self, baixa):
        from django.contrib.contenttypes.models import ContentType
        from dados_comuns.models import HistoricoGeral

        ct = ContentType.objects.get_for_model(BaixaFisicaBemPatrimonial)
        return HistoricoGeral.objects.filter(content_type=ct, object_id=str(baixa.pk)).count()

    def _criar_baixa_aceita_com_dois_bens(self, processo=None):
        baixa = self._nova_baixa_aceita(processo)
        for bem in (self.bem, self.bem2):
            self._vincular_bem_baixado(baixa, bem)
        return baixa

    def _post_corrigir(self, baixa, numero=None):
        return self.client.post(
            self.action_url(baixa.id, "corrigir-processo"),
            {"numero_processo_baixa": numero or self.PROCESSO_NOVO},
            format="json",
        )

    def _obter_historicos(self, baixa):
        from django.contrib.contenttypes.models import ContentType
        from dados_comuns.models import HistoricoGeral

        ct = ContentType.objects.get_for_model(BaixaFisicaBemPatrimonial)
        return list(
            HistoricoGeral.objects.filter(
                content_type=ct, object_id=str(baixa.pk)
            ).order_by("id")
        )

    def test_corrige_valido_propaga_para_bens(self):
        baixa = self._criar_baixa_aceita_com_bem()
        nome_antes = self.bem.nome
        status_bem_antes = self.bem.status
        total_antes = BaixaFisicaBemPatrimonial.objects.count()
        historico_antes = self._contar_historico(baixa)

        self._auth(self.gestor)
        resp = self._post_corrigir(baixa)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["numero_processo_baixa"], self.PROCESSO_NOVO)

        baixa.refresh_from_db()
        self.assertEqual(baixa.numero_processo_baixa, self.PROCESSO_NOVO)
        self.assertEqual(baixa.status, constants.ACEITA)
        self.assertEqual(BaixaFisicaBemPatrimonial.objects.count(), total_antes)

        self.bem.refresh_from_db()
        self.assertEqual(self.bem.numero_processo, self.PROCESSO_NOVO)
        self.assertEqual(self.bem.localizacao, f"Baixa Física - {self.PROCESSO_NOVO}")
        self.assertEqual(self.bem.status, status_bem_antes)
        self.assertEqual(self.bem.nome, nome_antes)
        self.assertTrue(
            BaixaFisicaBensItem.objects.filter(baixa=baixa, bem=self.bem).exists()
        )
        self.assertEqual(self._contar_historico(baixa), historico_antes + 1)
        historicos = self._obter_historicos(baixa)
        registro = historicos[-1]
        self.assertEqual(registro.campo, "numero_processo_baixa")
        self.assertEqual(registro.valor_antigo, self.PROCESSO_ANTIGO)
        self.assertEqual(registro.valor_novo, self.PROCESSO_NOVO)
        self.assertEqual(registro.alterado_por, self.gestor)
        self.assertIsNotNone(registro.alterado_em)

    def test_segunda_correcao_cria_segundo_registro_sem_alterar_primeiro(self):
        baixa = self._criar_baixa_aceita_com_bem()
        self._auth(self.gestor)
        resp1 = self._post_corrigir(baixa)
        self.assertEqual(resp1.status_code, status.HTTP_200_OK)
        primeiro = self._obter_historicos(baixa)[-1]
        primeiro_id = primeiro.id
        valor_primeiro_novo = primeiro.valor_novo

        segundo_numero = "6016.2025/0333333-3"
        resp2 = self._post_corrigir(baixa, numero=segundo_numero)
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)
        baixa.refresh_from_db()
        self.assertEqual(baixa.numero_processo_baixa, segundo_numero)

        historicos = self._obter_historicos(baixa)
        self.assertEqual(len(historicos), 2)
        primeiro_db = [h for h in historicos if h.id == primeiro_id][0]
        self.assertEqual(primeiro_db.valor_antigo, self.PROCESSO_ANTIGO)
        self.assertEqual(primeiro_db.valor_novo, valor_primeiro_novo)
        segundo = historicos[-1]
        self.assertEqual(segundo.campo, "numero_processo_baixa")
        self.assertEqual(segundo.valor_antigo, self.PROCESSO_NOVO)
        self.assertEqual(segundo.valor_novo, segundo_numero)
        self.assertEqual(segundo.alterado_por, self.gestor)
        self.assertIsNotNone(segundo.alterado_em)

    def test_historico_endpoint_exibe_correcao_com_usuario_e_data(self):
        baixa = self._criar_baixa_aceita_com_bem()
        self._auth(self.gestor)
        resp = self._post_corrigir(baixa)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        hist = self.client.get(self.action_url(baixa.id, "historico"))
        self.assertEqual(hist.status_code, status.HTTP_200_OK)
        self.assertTrue(hist.data)
        correcao = [r for r in hist.data if r["campo"] == "numero_processo_baixa"]
        self.assertTrue(correcao)
        registro = correcao[0]
        self.assertEqual(registro["valor_antigo"], self.PROCESSO_ANTIGO)
        self.assertEqual(registro["valor_novo"], self.PROCESSO_NOVO)
        self.assertEqual(registro["alterado_por"], self.gestor.username)
        self.assertIsNotNone(registro["data_alteracao"])

    def test_corrige_valido_com_dois_bens_e_preserva_outra_baixa(self):
        baixa = self._criar_baixa_aceita_com_dois_bens()
        outra = criar_baixa(
            self.ua, self.operador, status=constants.ACEITA,
            numero_processo_baixa="6016.2025/0999999-9",
        )
        bem_outra = criar_bem(
            self.ua, self.operador, numero_patrimonial="000.000000009-0",
            status=constants.BAIXA_FISICA, numero_processo="6016.2025/0999999-9",
            localizacao="Baixa Física - 6016.2025/0999999-9",
        )
        BaixaFisicaBensItem.objects.create(baixa=outra, bem=bem_outra)
        nome1, nome2 = self.bem.nome, self.bem2.nome

        self._auth(self.gestor)
        resp = self._post_corrigir(baixa)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.bem.refresh_from_db()
        self.bem2.refresh_from_db()
        bem_outra.refresh_from_db()
        outra.refresh_from_db()
        for bem in (self.bem, self.bem2):
            self.assertEqual(bem.numero_processo, self.PROCESSO_NOVO)
            self.assertEqual(bem.localizacao, f"Baixa Física - {self.PROCESSO_NOVO}")
            self.assertEqual(bem.status, constants.BAIXA_FISICA)
        self.assertEqual(self.bem.nome, nome1)
        self.assertEqual(self.bem2.nome, nome2)
        self.assertEqual(baixa.itens.count(), 2)
        self.assertEqual(bem_outra.numero_processo, "6016.2025/0999999-9")
        self.assertEqual(outra.numero_processo_baixa, "6016.2025/0999999-9")

    def test_detalhe_e_lista_exibem_numero_atualizado(self):
        baixa = self._criar_baixa_aceita_com_bem()
        self._auth(self.gestor)
        resp = self._post_corrigir(baixa)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        detalhe = self.client.get(self.detail_url(baixa.id))
        self.assertEqual(detalhe.status_code, status.HTTP_200_OK)
        self.assertEqual(detalhe.data["numero_processo_baixa"], self.PROCESSO_NOVO)
        lista = self.client.get(self.list_url)
        self.assertEqual(lista.status_code, status.HTTP_200_OK)
        resultados = lista.data.get("results", lista.data)
        item = next(b for b in resultados if b["id"] == baixa.id)
        self.assertEqual(item["numero_processo_baixa"], self.PROCESSO_NOVO)

    def test_falha_em_um_bem_reverte_tudo(self):
        baixa = self._criar_baixa_aceita_com_dois_bens()
        self._auth(self.gestor)
        original_save = BemPatrimonial.save

        def _side(inst_self, *args, **kwargs):
            if inst_self.pk == self.bem2.pk:
                raise RuntimeError("falha simulada no bem")
            return original_save(inst_self, *args, **kwargs)

        with patch.object(BemPatrimonial, "save", autospec=True) as mock_save:
            mock_save.side_effect = _side
            with self.assertRaises(RuntimeError):
                self._post_corrigir(baixa)
        baixa.refresh_from_db()
        self.bem.refresh_from_db()
        self.bem2.refresh_from_db()
        self.assertEqual(baixa.numero_processo_baixa, self.PROCESSO_ANTIGO)
        self.assertEqual(self.bem.numero_processo, self.PROCESSO_ANTIGO)
        self.assertEqual(self.bem2.numero_processo, self.PROCESSO_ANTIGO)
        self.assertEqual(self.bem.localizacao, f"Baixa Física - {self.PROCESSO_ANTIGO}")

    def test_formato_invalido_retorna_400_sem_alterar(self):
        baixa = self._criar_baixa_aceita_com_bem()
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(baixa.id, "corrigir-processo"),
            {"numero_processo_baixa": "NUMERO-RUIM"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        baixa.refresh_from_db()
        self.bem.refresh_from_db()
        self.assertEqual(baixa.numero_processo_baixa, self.PROCESSO_ANTIGO)
        self.assertEqual(self.bem.numero_processo, self.PROCESSO_ANTIGO)
        self.assertEqual(self._contar_historico(baixa), 0)

    def test_apos_nbbpm_vinculada_retorna_400(self):
        baixa = self._criar_baixa_aceita_com_bem()
        nbbpm = NBBPM.objects.create(
            numero="001.0000002/2026",
            numero_processo_baixa=self.PROCESSO_ANTIGO,
            data_autorizacao=timezone.localdate(),
            responsavel="G",
            criado_por=self.gestor,
        )
        nbbpm.baixas.set([baixa])
        self._auth(self.gestor)
        resp = self._post_corrigir(baixa)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        baixa.refresh_from_db()
        self.bem.refresh_from_db()
        self.assertEqual(baixa.numero_processo_baixa, self.PROCESSO_ANTIGO)
        self.assertEqual(self.bem.numero_processo, self.PROCESSO_ANTIGO)
        self.assertEqual(self._contar_historico(baixa), 0)

    def test_apos_numero_legado_retorna_400(self):
        baixa = self._criar_baixa_aceita_com_bem()
        baixa.numero_nbbpm = "001.0000003/2026"
        baixa.save(update_fields=["numero_nbbpm"])
        self._auth(self.gestor)
        resp = self._post_corrigir(baixa)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        baixa.refresh_from_db()
        self.bem.refresh_from_db()
        self.assertEqual(baixa.numero_processo_baixa, self.PROCESSO_ANTIGO)
        self.assertEqual(self.bem.numero_processo, self.PROCESSO_ANTIGO)
        self.assertEqual(self._contar_historico(baixa), 0)

    def test_status_nao_aceita_retorna_400(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.SOLICITADA)
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        processo_antes = self.bem.numero_processo
        self._auth(self.gestor)
        resp = self._post_corrigir(baixa)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.numero_processo, processo_antes)
        self.assertEqual(self._contar_historico(baixa), 0)

    def test_operador_nao_pode_corrigir_403(self):
        baixa = self._criar_baixa_aceita_com_bem()
        self._auth(self.operador)
        resp = self._post_corrigir(baixa)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        baixa.refresh_from_db()
        self.bem.refresh_from_db()
        self.assertEqual(baixa.numero_processo_baixa, self.PROCESSO_ANTIGO)
        self.assertEqual(self.bem.numero_processo, self.PROCESSO_ANTIGO)
        self.assertEqual(self._contar_historico(baixa), 0)

    def test_falha_em_um_bem_reverte_tudo_sem_historico(self):
        baixa = self._criar_baixa_aceita_com_dois_bens()
        historico_antes = self._contar_historico(baixa)
        self._auth(self.gestor)
        original_save = BemPatrimonial.save

        def _side(inst_self, *args, **kwargs):
            if inst_self.pk == self.bem2.pk:
                raise RuntimeError("falha simulada no bem")
            return original_save(inst_self, *args, **kwargs)

        with patch.object(BemPatrimonial, "save", autospec=True) as mock_save:
            mock_save.side_effect = _side
            with self.assertRaises(RuntimeError):
                self._post_corrigir(baixa)
        self.assertEqual(self._contar_historico(baixa), historico_antes)


class BaixaFisicaCorrigirProcessoModelTestCase(BaseSetup):
    def _baixa_aceita_com_bens_baixados(self):
        baixa = criar_baixa(
            self.ua, self.operador, status=constants.ACEITA,
            numero_processo_baixa="6016.2025/0117371-7",
        )
        for bem in (self.bem, self.bem2):
            BaixaFisicaBensItem.objects.create(baixa=baixa, bem=bem)
            bem.numero_processo = "6016.2025/0117371-7"
            bem.localizacao = "Baixa Física - 6016.2025/0117371-7"
            bem.status = constants.BAIXA_FISICA
            bem.save(update_fields=["numero_processo", "localizacao", "status"])
        return baixa

    def _contar_historico(self, baixa):
        from django.contrib.contenttypes.models import ContentType
        from dados_comuns.models import HistoricoGeral

        ct = ContentType.objects.get_for_model(BaixaFisicaBemPatrimonial)
        return HistoricoGeral.objects.filter(content_type=ct, object_id=str(baixa.pk))

    def test_corrigir_valido_propaga_para_bens(self):
        from django.core.exceptions import ValidationError

        baixa = self._baixa_aceita_com_bens_baixados()
        nome_antes = self.bem.nome

        baixa.corrigir_numero_processo("6016.2025/0333333-3", usuario=self.gestor)
        baixa.refresh_from_db()
        self.bem.refresh_from_db()
        self.bem2.refresh_from_db()
        self.assertEqual(baixa.numero_processo_baixa, "6016.2025/0333333-3")
        self.assertEqual(baixa.status, constants.ACEITA)
        for bem in (self.bem, self.bem2):
            self.assertEqual(bem.numero_processo, "6016.2025/0333333-3")
            self.assertEqual(bem.localizacao, "Baixa Física - 6016.2025/0333333-3")
            self.assertEqual(bem.status, constants.BAIXA_FISICA)
        self.assertEqual(self.bem.nome, nome_antes)
        self.assertEqual(baixa.itens.count(), 2)
        historicos = list(self._contar_historico(baixa).order_by("id"))
        self.assertEqual(len(historicos), 1)
        registro = historicos[0]
        self.assertEqual(registro.campo, "numero_processo_baixa")
        self.assertEqual(registro.valor_antigo, "6016.2025/0117371-7")
        self.assertEqual(registro.valor_novo, "6016.2025/0333333-3")
        self.assertEqual(registro.alterado_por, self.gestor)
        self.assertIsNotNone(registro.alterado_em)

    def test_segunda_correcao_gera_novo_registro_imutavel(self):
        baixa = self._baixa_aceita_com_bens_baixados()
        baixa.corrigir_numero_processo("6016.2025/0333333-3", usuario=self.gestor)
        primeiro = list(self._contar_historico(baixa).order_by("id"))[0]
        baixa.corrigir_numero_processo("6016.2025/0444444-4", usuario=self.gestor)
        historicos = list(self._contar_historico(baixa).order_by("id"))
        self.assertEqual(len(historicos), 2)
        primeiro.refresh_from_db()
        self.assertEqual(primeiro.valor_antigo, "6016.2025/0117371-7")
        self.assertEqual(primeiro.valor_novo, "6016.2025/0333333-3")
        segundo = historicos[1]
        self.assertEqual(segundo.valor_antigo, "6016.2025/0333333-3")
        self.assertEqual(segundo.valor_novo, "6016.2025/0444444-4")
        self.assertEqual(segundo.alterado_por, self.gestor)

    def test_corrigir_falha_em_bem_reverte_tudo(self):
        baixa = self._baixa_aceita_com_bens_baixados()

        original_save = BemPatrimonial.save

        def _falha(inst_self, *args, **kwargs):
            if inst_self.pk == self.bem2.pk:
                raise RuntimeError("falha simulada")
            return original_save(inst_self, *args, **kwargs)

        with patch.object(BemPatrimonial, "save", autospec=True) as mock_save:
            mock_save.side_effect = lambda inst_self, *a, **k: _falha(inst_self, *a, **k)
            with self.assertRaises(RuntimeError):
                baixa.corrigir_numero_processo("6016.2025/0333333-3")
        baixa.refresh_from_db()
        self.bem.refresh_from_db()
        self.bem2.refresh_from_db()
        self.assertEqual(baixa.numero_processo_baixa, "6016.2025/0117371-7")
        self.assertEqual(self.bem.numero_processo, "6016.2025/0117371-7")
        self.assertEqual(self.bem2.numero_processo, "6016.2025/0117371-7")

    def test_corrigir_status_invalido_levanta_erro(self):
        from django.core.exceptions import ValidationError

        baixa = criar_baixa(self.ua, self.operador, status=constants.SOLICITADA)
        with self.assertRaises(ValidationError):
            baixa.corrigir_numero_processo("6016.2025/0333333-3")

    def test_corrigir_formato_invalido_levanta_erro(self):
        from django.core.exceptions import ValidationError

        baixa = criar_baixa(
            self.ua, self.operador, status=constants.ACEITA,
            numero_processo_baixa="6016.2025/0117371-7",
        )
        with self.assertRaises(ValidationError):
            baixa.corrigir_numero_processo("RUIM")


class BaixaConsultaAposNBBPMTestCase(BaseAPISetup):
    """Cobre: identificador na baixa e evento por baixa."""

    PROCESSO = "6016.2025/0117371-7"

    def _nova_baixa_aceita_com_bem(self, processo=None, npat="000.000000001-0"):
        bem = criar_bem(self.ua, self.operador, numero_patrimonial=npat)
        baixa = criar_baixa(
            self.ua, self.operador, status=constants.ACEITA,
            numero_processo_baixa=processo or self.PROCESSO,
        )
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=bem)
        return baixa, bem

    def _payload(self, baixas):
        return {
            "baixas": [b.id for b in baixas],
            "numero_processo_baixa": self.PROCESSO,
            "data_autorizacao": str(timezone.localdate()),
            "responsavel": "Gestor Teste",
        }

    def _historicos_baixa(self, baixa):
        from django.contrib.contenttypes.models import ContentType
        from dados_comuns.models import HistoricoGeral

        ct = ContentType.objects.get_for_model(BaixaFisicaBemPatrimonial)
        return HistoricoGeral.objects.filter(content_type=ct, object_id=str(baixa.pk)).order_by("id")

    def test_geracao_cria_vinculo_historico_identificador_e_reemissao(self):
        baixa1, _ = self._nova_baixa_aceita_com_bem(npat="000.000000021-0")
        baixa2, _ = self._nova_baixa_aceita_com_bem(npat="000.000000022-0")
        baixa_sem_nota = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        self._auth(self.gestor)

        resp = self.client.post("/api/nbbpm/", self._payload([baixa1, baixa2]), format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        numero = resp.data["numero"]
        nbbpm_id = resp.data["id"]

        for baixa in (baixa1, baixa2):
            baixa.refresh_from_db()
            self.assertTrue(baixa.nbbpms_lote.filter(pk=nbbpm_id).exists())

        data_br = timezone.localdate().strftime("%d/%m/%Y")
        rotulo_uo = f"{self.uo.codigo} - {self.uo.nome}"
        for baixa in (baixa1, baixa2):
            eventos = [h for h in self._historicos_baixa(baixa) if h.campo == "nbbpm"]
            self.assertEqual(len(eventos), 1)
            ev = eventos[0]
            self.assertEqual(ev.valor_novo, numero)
            self.assertEqual(ev.alterado_por, self.gestor)
            self.assertIsNotNone(ev.alterado_em)
            self.assertIn(numero, ev.justificativa)
            self.assertIn(self.PROCESSO, ev.justificativa)
            self.assertIn(data_br, ev.justificativa)
            self.assertIn(rotulo_uo, ev.justificativa)

        lista = self.client.get(self.list_url)
        item = next(b for b in lista.data.get("results", lista.data) if b["id"] == baixa1.id)
        self.assertEqual(item["numero_nbbpm"], numero)
        self.assertEqual(item["nbbpm_id"], nbbpm_id)

        detalhe = self.client.get(self.detail_url(baixa1.id))
        self.assertEqual(detalhe.data["numero_nbbpm"], numero)
        self.assertEqual(detalhe.data["nbbpm_id"], nbbpm_id)
        self.assertTrue(detalhe.data["itens"])
        self.assertIsNotNone(detalhe.data["url_gerar_nbbpm"])

        hist = self.client.get(self.action_url(baixa1.id, "historico"))
        evento_api = next(r for r in hist.data if r["campo"] == "nbbpm")
        self.assertEqual(evento_api["valor_novo"], numero)
        self.assertEqual(evento_api["alterado_por"], self.gestor.username)

        hist_antes = self._historicos_baixa(baixa1).count()
        pdf = self.client.get(f"/api/nbbpm/{nbbpm_id}/pdf/")
        self.assertEqual(pdf.status_code, status.HTTP_200_OK)
        self.assertEqual(self._historicos_baixa(baixa1).count(), hist_antes)

        detalhe_sem_nota = self.client.get(self.detail_url(baixa_sem_nota.id))
        self.assertIsNone(detalhe_sem_nota.data["nbbpm_id"])
        self.assertEqual(detalhe_sem_nota.data["numero_nbbpm"], "")

    def test_segunda_geracao_400_mantem_vinculo_e_historico(self):
        baixa1, _ = self._nova_baixa_aceita_com_bem(npat="000.000000031-0")
        baixa2, _ = self._nova_baixa_aceita_com_bem(npat="000.000000032-0")
        self._auth(self.gestor)

        resp1 = self.client.post("/api/nbbpm/", self._payload([baixa1, baixa2]), format="json")
        self.assertEqual(resp1.status_code, status.HTTP_201_CREATED)
        nbbpm_id1 = resp1.data["id"]
        hist_antes = self._historicos_baixa(baixa1).count()
        total_antes = NBBPM.objects.count()

        resp2 = self.client.post("/api/nbbpm/", self._payload([baixa1]), format="json")
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(NBBPM.objects.count(), total_antes)
        baixa1.refresh_from_db()
        self.assertEqual(list(baixa1.nbbpms_lote.values_list("id", flat=True)), [nbbpm_id1])
        self.assertEqual(self._historicos_baixa(baixa1).count(), hist_antes)

    def test_falha_no_historico_desfaz_nbbpm_e_vinculo(self):
        from dados_comuns.models import HistoricoGeral
        from bem_patrimonial.services.nbbpm_numero import criar_nbbpm_com_retry

        baixa1, _ = self._nova_baixa_aceita_com_bem(npat="000.000000033-0")
        total_antes = NBBPM.objects.count()
        hist_antes = self._historicos_baixa(baixa1).count()

        with patch.object(HistoricoGeral.objects, "bulk_create", side_effect=RuntimeError("falha historico")):
            with self.assertRaises(RuntimeError):
                criar_nbbpm_com_retry(
                    baixas=[baixa1],
                    numero_processo_baixa=self.PROCESSO,
                    data_autorizacao=timezone.localdate(),
                    responsavel="Gestor Teste",
                    criado_por=self.gestor,
                )
        self.assertEqual(NBBPM.objects.count(), total_antes)
        baixa1.refresh_from_db()
        self.assertFalse(baixa1.nbbpms_lote.exists())
        self.assertEqual(self._historicos_baixa(baixa1).count(), hist_antes)
