from unittest.mock import patch

from django.contrib.auth.models import Group
from django.urls import reverse
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from bem_patrimonial import constants
from bem_patrimonial.models import BemPatrimonial, MovimentacaoBemPatrimonial, MovimentacaoBensItem
from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua, codigo_uo
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario


class MovimentacaoApiTestCase(TestCase):
    def setUp(self):
        self.uo_origem = criar_uo(
            codigo=codigo_uo(1, 16, 28),
            nome="UO Origem",
            sigla="UOO",
        )
        self.ua_origem = criar_ua(
            uo=self.uo_origem,
            codigo=codigo_ua(1, 16, 28, 1),
            sigla="UA1",
            nome="UA Origem",
        )
        self.ua_destino = criar_ua(
            uo=self.uo_origem,
            codigo=codigo_ua(1, 16, 28, 2),
            sigla="UA2",
            nome="UA Destino",
        )
        self.uo_outra = criar_uo(
            codigo=codigo_uo(2, 20, 30),
            nome="UO Outra",
            sigla="UOO2",
        )
        self.ua_outra_origem = criar_ua(
            uo=self.uo_outra,
            codigo=codigo_ua(2, 20, 30, 1),
            sigla="UA3",
            nome="UA Outra Origem",
        )
        self.ua_outra_destino = criar_ua(
            uo=self.uo_outra,
            codigo=codigo_ua(2, 20, 30, 2),
            sigla="UA4",
            nome="UA Outra Destino",
        )

        self.grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.grupo_operador, _ = Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)

        self.operador_origem = self._criar_usuario(
            "operador_origem",
            self.uo_origem,
            self.ua_origem,
            self.grupo_operador,
        )
        self.gestor_origem = self._criar_usuario(
            "gestor_origem",
            self.uo_origem,
            self.ua_destino,
            self.grupo_gestor,
            is_staff=True,
        )
        self.operador_outra = self._criar_usuario(
            "operador_outra",
            self.uo_outra,
            self.ua_outra_origem,
            self.grupo_operador,
        )
        self.usuaria_sem_grupo = self._criar_usuario(
            "sem_grupo",
            self.uo_origem,
            self.ua_origem,
            is_staff=True,
        )

        self.bem_visivel = self._criar_bem(
            "001.000000001-1",
            self.ua_origem,
            criado_por=self.operador_origem,
        )
        self.bem_oculto = self._criar_bem(
            "002.000000001-1",
            self.ua_outra_origem,
            criado_por=self.operador_outra,
        )
        self.bem_api = self._criar_bem(
            "001.000000002-2",
            self.ua_origem,
            criado_por=self.operador_origem,
        )

        with patch("bem_patrimonial.models.envia_email_nova_solicitacao_movimentacao"):
            self.mov_visivel = self._criar_movimentacao(
                bem=self.bem_visivel,
                ua_origem=self.ua_origem,
                ua_destino=self.ua_destino,
                solicitado_por=self.operador_origem,
            )
            self.mov_oculta = self._criar_movimentacao(
                bem=self.bem_oculto,
                ua_origem=self.ua_outra_origem,
                ua_destino=self.ua_outra_destino,
                solicitado_por=self.operador_outra,
            )

        self.client = APIClient()

        self.patch_email_aprovada = patch(
            "bem_patrimonial.movimentacao_api_views.envia_email_solicitacao_movimentacao_aceita"
        )
        self.patch_email_rejeitada = patch(
            "bem_patrimonial.movimentacao_api_views.envia_email_solicitacao_movimentacao_rejeitada"
        )
        self.patch_email_cancelada = patch(
            "bem_patrimonial.movimentacao_api_views.envia_email_solicitacao_movimentacao_cancelada"
        )
        self.mock_email_aprovada = self.patch_email_aprovada.start()
        self.mock_email_rejeitada = self.patch_email_rejeitada.start()
        self.mock_email_cancelada = self.patch_email_cancelada.start()

    def tearDown(self):
        patch.stopall()

    def _criar_usuario(self, username, uo, ua, grupo=None, **kwargs):
        usuario = Usuario.objects.create_user(
            username=username,
            email=f"{username}@test.com",
            **auth_kwargs("test123"),
            unidade_orcamentaria=uo,
            unidade_administrativa=ua,
            **kwargs,
        )
        if grupo is not None:
            usuario.groups.add(grupo)
        return usuario

    def _criar_bem(self, numero_patrimonial, ua, criado_por):
        return BemPatrimonial.objects.create(
            numero_patrimonial=numero_patrimonial,
            nome=f"Bem {numero_patrimonial}",
            descricao="Bem para teste de API",
            valor_unitario=1000,
            marca="Dell",
            modelo="Latitude",
            numero_processo=f"PROC-{numero_patrimonial}",
            localizacao="Sala 1",
            criado_por=criado_por,
            status=constants.APROVADO,
            unidade_administrativa=ua,
        )

    def _criar_movimentacao(self, bem, ua_origem, ua_destino, solicitado_por):
        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=ua_origem,
            unidade_administrativa_destino=ua_destino,
            solicitado_por=solicitado_por,
            status=constants.ENVIADA,
        )
        MovimentacaoBensItem.objects.create(movimentacao=movimentacao, bem=bem)
        movimentacao.refresh_from_db()
        return movimentacao

    def _autenticar(self, usuario):
        self.client.force_authenticate(user=usuario)

    def _lista_movimentacoes(self, response):
        if isinstance(response.data, dict) and "results" in response.data:
            return response.data["results"]
        return response.data

    def test_listagem_respeita_escopo_do_usuario(self):
        self._autenticar(self.gestor_origem)

        response = self.client.get(reverse("movimentacoes-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in self._lista_movimentacoes(response)}
        self.assertIn(self.mov_visivel.id, ids)
        self.assertNotIn(self.mov_oculta.id, ids)

    def test_usuario_sem_permissao_nao_acessa_api(self):
        self._autenticar(self.usuaria_sem_grupo)

        response = self.client.get(reverse("movimentacoes-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_usuario_fora_do_escopo_nao_retrata_nem_aprova_movimentacao(self):
        self._autenticar(self.operador_outra)

        retrieve = self.client.get(
            reverse("movimentacoes-detail", kwargs={"pk": self.mov_visivel.pk})
        )
        aprovar = self.client.post(
            reverse("movimentacoes-aprovar", kwargs={"pk": self.mov_visivel.pk})
        )

        self.assertEqual(retrieve.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(aprovar.status_code, status.HTTP_404_NOT_FOUND)

    def test_acao_em_movimentacao_ja_processada_retorna_400(self):
        self._autenticar(self.operador_origem)

        payload = {
            "unidade_administrativa_origem": self.ua_origem.id,
            "unidade_administrativa_destino": self.ua_destino.id,
            "observacao": "Movimentação para estado final",
            "itens": [{"bem": self.bem_api.id}],
        }
        response = self.client.post(reverse("movimentacoes-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        movimentacao_id = response.data["id"]
        self._autenticar(self.gestor_origem)
        aprovar = self.client.post(reverse("movimentacoes-aprovar", kwargs={"pk": movimentacao_id}))
        self.assertEqual(aprovar.status_code, status.HTTP_200_OK)

        rejeitar = self.client.post(reverse("movimentacoes-rejeitar", kwargs={"pk": movimentacao_id}))
        cancelar = self.client.post(reverse("movimentacoes-cancelar", kwargs={"pk": movimentacao_id}))

        self.assertEqual(rejeitar.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(cancelar.status_code, status.HTTP_400_BAD_REQUEST)

    def test_criacao_aprovacao_historico_e_documento_cimbpm(self):
        self._autenticar(self.operador_origem)
        payload = {
            "unidade_administrativa_origem": self.ua_origem.id,
            "unidade_administrativa_destino": self.ua_destino.id,
            "observacao": "Movimentação criada pela API",
            "itens": [{"bem": self.bem_api.id}],
        }

        response = self.client.post(reverse("movimentacoes-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        movimentacao_id = response.data["id"]

        self._autenticar(self.gestor_origem)
        aprovar = self.client.post(reverse("movimentacoes-aprovar", kwargs={"pk": movimentacao_id}))
        self.assertEqual(aprovar.status_code, status.HTTP_200_OK)
        self.assertEqual(aprovar.data["status"], constants.ACEITA)

        historico = self.client.get(
            reverse("movimentacoes-historico", kwargs={"pk": movimentacao_id})
        )
        self.assertEqual(historico.status_code, status.HTTP_200_OK)
        self.assertTrue(historico.data)
        self.assertTrue(
            any(
                any(acao["campo"] == "status" for acao in grupo["acoes"])
                for grupo in historico.data
            )
        )

        documento = self.client.get(
            reverse("movimentacoes-documento-cimbpm", kwargs={"pk": movimentacao_id})
        )
        self.assertEqual(documento.status_code, status.HTTP_200_OK)
        self.assertEqual(documento["Content-Type"], "application/pdf")
        self.assertIn("attachment", documento["Content-Disposition"])

    def test_patch_permite_apenas_observacao(self):
        self._autenticar(self.operador_origem)
        payload = {
            "unidade_administrativa_origem": self.ua_origem.id,
            "unidade_administrativa_destino": self.ua_destino.id,
            "observacao": "Movimentação para edição",
            "itens": [{"bem": self.bem_api.id}],
        }

        response = self.client.post(reverse("movimentacoes-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        movimentacao_id = response.data["id"]
        patch_response = self.client.patch(
            reverse("movimentacoes-detail", kwargs={"pk": movimentacao_id}),
            {"observacao": "Observação atualizada"},
            format="json",
        )

        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.data["observacao"], "Observação atualizada")

    def test_criacao_rejeita_payload_invalido(self):
        self._autenticar(self.operador_origem)
        payload = {
            "unidade_administrativa_origem": self.ua_origem.id,
            "unidade_administrativa_destino": self.ua_destino.id,
            "observacao": "Movimentação inválida",
            "itens": [],
        }

        response = self.client.post(reverse("movimentacoes-list"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("itens", response.data)

    def test_endpoints_de_detalhe_retorno_404_para_pk_inexistente(self):
        self._autenticar(self.operador_origem)

        retrieve = self.client.get(reverse("movimentacoes-detail", kwargs={"pk": 999999}))
        historico = self.client.get(
            reverse("movimentacoes-historico", kwargs={"pk": 999999})
        )
        documento = self.client.get(
            reverse("movimentacoes-documento-cimbpm", kwargs={"pk": 999999})
        )

        self.assertEqual(retrieve.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(historico.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(documento.status_code, status.HTTP_404_NOT_FOUND)
