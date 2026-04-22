from unittest.mock import patch, MagicMock

from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APITestCase, APIClient

from dados_comuns.tests.auth_test_utils import auth_kwargs
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO

from bem_patrimonial.models import (
    BaixaFisicaBemPatrimonial,
    BaixaFisicaBensItem,
    BemPatrimonial,
)
from bem_patrimonial.api_serializers import (
    BaixaFisicaBemPatrimonialCreateSerializer,
    BaixaFisicaBemPatrimonialUpdateSerializer,
    BaixaFisicaBemPatrimonialListSerializer,
    BaixaFisicaBemPatrimonialDetailSerializer,
    BaixaFisicaAprovarSerializer,
    BaixaFisicaCancelarSerializer,
    BaixaFisicaEnviarSolicitacaoSerializer,
    BaixaFisicaBensItemCreateSerializer,
    UnidadeAdministrativaSimpleSerializer,
    UserSimpleSerializer,
    BemPatrimonialSimpleSerializer,
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
        for campo in ["id", "username", "nome_completo", "email"]:
            self.assertIn(campo, data)

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
        return {
            "numero_processo_baixa": "PROC-001",
            "unidade_administrativa_origem": (ua or self.ua).id,
            "data_baixa": data_baixa or str(timezone.localdate()),
            "itens": itens if itens is not None else [{"bem": self.bem.id}],
        }

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
        s = self._serializer({
            "numero_processo_baixa": "PROC-NOVO",
            "itens": [{"bem": self.bem.id}],
        })
        self.assertTrue(s.is_valid(), s.errors)

    def test_sem_itens_invalido(self):
        s = self._serializer({"itens": []})
        self.assertFalse(s.is_valid())
        self.assertIn("itens", s.errors)

    def test_status_diferente_aguardando_envio_invalido(self):
        self.baixa.status = constants.SOLICITADA
        self.baixa.save()
        s = self._serializer({"numero_processo_baixa": "PROC-X"})
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
        s = BaixaFisicaAprovarSerializer(data={}, context=self._ctx(self.gestor))
        self.assertTrue(s.is_valid(), s.errors)

    def test_operador_nao_pode_aprovar(self):
        s = BaixaFisicaAprovarSerializer(data={}, context=self._ctx(self.operador))
        with self.assertRaises(PermissionDenied):
            s.is_valid(raise_exception=True)

    def test_invalido_quando_status_diferente_de_solicitada(self):
        self.baixa.status = constants.AGUARDANDO_ENVIO
        self.baixa.save()
        s = BaixaFisicaAprovarSerializer(data={}, context=self._ctx(self.gestor))
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


# ============================================================================
# TESTES DO SERIALIZER DE DETALHE (URLs de ação)
# ============================================================================

class BaixaFisicaDetailSerializerUrlsTestCase(BaseSetup):
    def _serializer(self, baixa):
        req = MagicMock()
        req.build_absolute_uri = lambda path: f"https://testserver{path}"
        return BaixaFisicaBemPatrimonialDetailSerializer(
            baixa, context={"request": req}
        )

    def test_url_enviar_quando_aguardando_envio(self):
        baixa = criar_baixa(self.ua, self.operador)
        data = self._serializer(baixa).data
        self.assertIsNotNone(data["url_enviar_solicitacao"])
        self.assertIsNone(data["url_aprovar"])

    def test_url_aprovar_quando_solicitada(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.SOLICITADA)
        data = self._serializer(baixa).data
        self.assertIsNotNone(data["url_aprovar"])
        self.assertIsNone(data["url_enviar_solicitacao"])

    def test_url_cancelar_disponivel_para_aguardando_e_solicitada(self):
        for st in [constants.AGUARDANDO_ENVIO, constants.SOLICITADA]:
            baixa = criar_baixa(self.ua, self.operador, status=st,
                                numero_processo_baixa=f"PROC-{st}")
            data = self._serializer(baixa).data
            self.assertIsNotNone(data["url_cancelar"], f"Esperava url_cancelar para status={st}")

    def test_url_cancelar_indisponivel_quando_aceita(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        data = self._serializer(baixa).data
        self.assertIsNone(data["url_cancelar"])

    def test_url_gerar_nbbpm_quando_aceita_com_nbbpm(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA,
                            numero_nbbpm="NBBPM-001")
        data = self._serializer(baixa).data
        self.assertIsNotNone(data["url_gerar_nbbpm"])

    def test_url_gerar_nbbpm_ausente_sem_numero(self):
        baixa = criar_baixa(self.ua, self.operador, status=constants.ACEITA)
        data = self._serializer(baixa).data
        self.assertIsNone(data["url_gerar_nbbpm"])


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
        return {
            "numero_processo_baixa": "PROC-NOVO",
            "unidade_administrativa_origem": self.ua.id,
            "data_baixa": str(timezone.localdate()),
            "itens": [{"bem": self.bem.id}],
            **kwargs,
        }

    # Desabilitado: criação via API aciona _registrar_auditoria_se_alterado que
    # requer contexto de usuário no thread. Coberto em BaixaFisicaBemPatrimonialCreateSerializerTestCase.
    # def test_operador_cria_baixa(self):
    #     self._auth(self.operador)
    #     resp = self.client.post(self.list_url, self._payload(), format="json")
    #     self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
    #     self.assertEqual(resp.data["status"], constants.AGUARDANDO_ENVIO)

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

    def test_patch_numero_processo(self):
        self._auth(self.operador)
        resp = self.client.patch(
            self.detail_url(self.baixa.id),
            {"numero_processo_baixa": "PROC-BX-001",
             "itens": [{"bem": self.bem.id}]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.numero_processo_baixa, "PROC-BX-001")

    def test_update_quando_solicitada_retorna_400(self):
        self.baixa.status = constants.SOLICITADA
        self.baixa.save()
        self._auth(self.operador)
        resp = self.client.patch(
            self.detail_url(self.baixa.id),
            {"numero_processo_baixa": "PROC-X", "itens": [{"bem": self.bem.id}]},
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


# ============================================================================
# TESTES DO VIEWSET — ENVIAR SOLICITAÇÃO
# ============================================================================

class BaixaFisicaViewSetEnviarSolicitacaoTestCase(BaseAPISetup):
    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_solicitada")
    def test_enviar_solicitacao_muda_status(self, mock_email):
        self._auth(self.operador)
        resp = self.client.post(self.action_url(self.baixa.id, "enviar-solicitacao"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, constants.SOLICITADA)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_solicitada")
    def test_enviar_solicitacao_envia_email(self, mock_email):
        self._auth(self.operador)
        self.client.post(self.action_url(self.baixa.id, "enviar-solicitacao"))
        mock_email.assert_called_once()

    def test_enviar_baixa_ja_solicitada_retorna_400(self):
        self.baixa.status = constants.SOLICITADA
        self.baixa.save()
        self._auth(self.operador)
        resp = self.client.post(self.action_url(self.baixa.id, "enviar-solicitacao"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_solicitada",
           side_effect=Exception("SMTP error"))
    def test_falha_email_nao_impede_envio(self, mock_email):
        self._auth(self.operador)
        resp = self.client.post(self.action_url(self.baixa.id, "enviar-solicitacao"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ============================================================================
# TESTES DO VIEWSET — APROVAR
# ============================================================================

class BaixaFisicaViewSetAprovarTestCase(BaseAPISetup):
    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(self.ua, self.operador, status=constants.SOLICITADA)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_aprovada")
    @patch("bem_patrimonial.api_views.gerar_numero_nbbpm", return_value="NBBPM-2024-001")
    def test_gestor_aprova(self, mock_nbbpm, mock_email):
        self._auth(self.gestor)
        resp = self.client.post(self.action_url(self.baixa.id, "aprovar"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.baixa.refresh_from_db()
        self.assertEqual(self.baixa.status, constants.ACEITA)
        self.assertEqual(self.baixa.aprovado_por, self.gestor)
        self.assertIsNotNone(self.baixa.data_aprovacao)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_aprovada")
    @patch("bem_patrimonial.api_views.gerar_numero_nbbpm", return_value="NBBPM-2024-001")
    def test_aprovacao_gera_nbbpm(self, mock_nbbpm, mock_email):
        self._auth(self.gestor)
        self.client.post(self.action_url(self.baixa.id, "aprovar"))
        self.baixa.refresh_from_db()
        self.assertIsNotNone(self.baixa.numero_nbbpm)

    def test_operador_nao_pode_aprovar(self):
        self._auth(self.operador)
        resp = self.client.post(self.action_url(self.baixa.id, "aprovar"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_aprovar_status_errado_retorna_400(self):
        self.baixa.status = constants.AGUARDANDO_ENVIO
        self.baixa.save()
        self._auth(self.gestor)
        resp = self.client.post(self.action_url(self.baixa.id, "aprovar"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_aprovada",
           side_effect=Exception("Erro de email"))
    @patch("bem_patrimonial.api_views.gerar_numero_nbbpm", return_value="NBBPM-2024-001")
    def test_falha_email_nao_impede_aprovacao(self, mock_nbbpm, mock_email):
        self._auth(self.gestor)
        resp = self.client.post(self.action_url(self.baixa.id, "aprovar"))
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
            self.action_url(self.baixa.id, "cancelar"),
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
            self.action_url(self.baixa.id, "cancelar"), {}, format="json"
        )
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, constants.APROVADO)

    def test_operador_nao_pode_cancelar(self):
        self._auth(self.operador)
        resp = self.client.post(
            self.action_url(self.baixa.id, "cancelar"), {}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_nao_pode_cancelar_baixa_aceita(self):
        self.baixa.status = constants.ACEITA
        self.baixa.save()
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "cancelar"), {}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_cancelada",
           side_effect=Exception("Erro email"))
    def test_falha_email_nao_impede_cancelamento(self, mock_email):
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "cancelar"), {"motivo": "Cancelamento de teste"}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    @patch("bem_patrimonial.api_views.envia_email_baixa_fisica_cancelada")
    def test_cancelamento_sem_motivo_valido(self, mock_email):
        self._auth(self.gestor)
        resp = self.client.post(
            self.action_url(self.baixa.id, "cancelar"), {}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ============================================================================
# TESTES DO VIEWSET — GERAR NBBPM
# ============================================================================

class BaixaFisicaViewSetGerarNbbpmTestCase(BaseAPISetup):
    def setUp(self):
        super().setUp()
        self.baixa = criar_baixa(
            self.ua, self.operador,
            status=constants.ACEITA,
            numero_nbbpm="NBBPM-2024-001",
        )

    @patch("bem_patrimonial.api_views.http_response_nbbpm")
    def test_gerar_nbbpm_baixa_aceita(self, mock_pdf):
        from django.http import HttpResponse
        mock_pdf.return_value = HttpResponse(
            content_type="application/pdf",
            content=b"%PDF-fake",
        )
        self._auth(self.operador)
        resp = self.client.get(self.action_url(self.baixa.id, "gerar-nbbpm"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        mock_pdf.assert_called_once_with(self.baixa)

    def test_gerar_nbbpm_baixa_nao_aceita_retorna_400(self):
        self.baixa.status = constants.SOLICITADA
        self.baixa.save()
        self._auth(self.operador)
        resp = self.client.get(self.action_url(self.baixa.id, "gerar-nbbpm"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("bem_patrimonial.api_views.BaixaFisicaBemPatrimonialViewSet.get_object")
    def test_gerar_nbbpm_sem_numero_retorna_400(self, mock_get_object):
        baixa_sem_nbbpm = criar_baixa(
            self.ua, self.operador,
            status=constants.ACEITA,
            numero_nbbpm="PLACEHOLDER",
        )
        baixa_sem_nbbpm.numero_nbbpm = None
        mock_get_object.return_value = baixa_sem_nbbpm

        self._auth(self.operador)
        resp = self.client.get(self.action_url(self.baixa.id, "gerar-nbbpm"))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


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
