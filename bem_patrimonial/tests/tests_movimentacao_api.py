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
        self.ua_ponto_central = criar_ua(
            uo=self.uo_origem,
            codigo="001",
            sigla="PC",
            nome="Ponto Central",
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

    def _criar_bem(self, numero_patrimonial, ua, criado_por, **kwargs):
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
            **kwargs,
        )

    def _criar_movimentacao(
        self,
        bem=None,
        ua_origem=None,
        ua_destino=None,
        solicitado_por=None,
        com_item=True,
        bens=None,
    ):
        movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=ua_origem,
            unidade_administrativa_destino=ua_destino,
            solicitado_por=solicitado_por,
            status=constants.ENVIADA,
        )
        if com_item:
            if bens is not None:
                itens = bens
            elif bem is not None:
                itens = [bem]
            else:
                itens = []
            for bem_item in itens:
                MovimentacaoBensItem.objects.create(
                    movimentacao=movimentacao,
                    bem=bem_item,
                )
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

    def test_opcoes_cadastro_exibem_uos_ativas_com_ponto_central(self):
        url = reverse("movimentacoes-opcoes-cadastro")

        for user in (self.gestor_origem, self.operador_origem):
            with self.subTest(user=user.username):
                self._autenticar(user)

                response = self.client.get(url)

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                uos = {uo["id"]: uo for uo in response.data}
                self.assertIn(self.uo_origem.id, uos)
                self.assertIn(self.uo_outra.id, uos)
                self.assertTrue(uos[self.uo_origem.id]["tem_ponto_central"])
                self.assertIsInstance(uos[self.uo_outra.id]["tem_ponto_central"], bool)

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

    def test_operador_pode_cancelar_sua_propria_movimentacao_pendente(self):
        self._autenticar(self.operador_origem)

        response = self.client.post(
            reverse("movimentacoes-cancelar", kwargs={"pk": self.mov_visivel.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.mov_visivel.refresh_from_db()
        self.assertEqual(self.mov_visivel.status, constants.CANCELADA)
        self.assertEqual(self.mov_visivel.cancelado_por_id, self.operador_origem.pk)

    def test_gestor_pode_cancelar_movimentacao_entre_uos_mesmo_com_unidade_inativa(self):
        movimentacao = self._criar_movimentacao(
            bem=self.bem_api,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_outra_destino,
            solicitado_por=self.operador_origem,
        )
        self.ua_outra_destino.status = self.ua_outra_destino.INATIVA
        self.ua_outra_destino.save(update_fields=["status"])

        gestor_sem_ua_origem = self._criar_usuario(
            "gestor_sem_ua_origem",
            self.uo_origem,
            None,
            self.grupo_gestor,
            is_staff=True,
        )
        self._autenticar(gestor_sem_ua_origem)
        response = self.client.post(
            reverse("movimentacoes-cancelar", kwargs={"pk": movimentacao.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        movimentacao.refresh_from_db()
        self.assertEqual(movimentacao.status, constants.CANCELADA)
        self.assertEqual(movimentacao.cancelado_por_id, gestor_sem_ua_origem.pk)

    def test_gestor_da_uo_destino_tambem_pode_cancelar_movimentacao_entre_uos(self):
        movimentacao = self._criar_movimentacao(
            bem=self.bem_api,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_outra_destino,
            solicitado_por=self.operador_origem,
        )
        gestor_sem_ua_destino = self._criar_usuario(
            "gestor_sem_ua_destino",
            self.uo_outra,
            None,
            self.grupo_gestor,
            is_staff=True,
        )

        self._autenticar(gestor_sem_ua_destino)
        response = self.client.post(
            reverse("movimentacoes-cancelar", kwargs={"pk": movimentacao.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        movimentacao.refresh_from_db()
        self.assertEqual(movimentacao.status, constants.CANCELADA)
        self.assertEqual(movimentacao.cancelado_por_id, gestor_sem_ua_destino.pk)

    def test_operador_nao_autor_nao_pode_cancelar_solicitacao_de_outra_pessoa(self):
        outro_operador = self._criar_usuario(
            "outro_operador",
            self.uo_origem,
            self.ua_origem,
            self.grupo_operador,
        )

        self._autenticar(outro_operador)
        response = self.client.post(
            reverse("movimentacoes-cancelar", kwargs={"pk": self.mov_visivel.pk})
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(
            "você só pode cancelar movimentações criadas por você",
            str(response.data),
        )

    def test_filtro_por_intervalo_nao_retorna_movimentacao_quando_faixa_fica_dividida(self):
        bem_abaixo = self._criar_bem("100.000000000-0", self.ua_origem, self.operador_origem)
        bem_acima = self._criar_bem("900.000000000-0", self.ua_origem, self.operador_origem)
        movimentacao = self._criar_movimentacao(
            bem=bem_abaixo,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
            bens=[bem_abaixo, bem_acima],
        )

        self._autenticar(self.gestor_origem)
        response = self.client.get(
            reverse("movimentacoes-list"),
            {
                "numero_patrimonial_inicial": "500.000000000-0",
                "numero_patrimonial_final": "600.000000000-0",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in self._lista_movimentacoes(response)}
        self.assertNotIn(movimentacao.id, ids)

    def test_filtro_por_intervalo_retornando_um_item_dentro_da_faixa(self):
        bem_abaixo = self._criar_bem("100.000000001-1", self.ua_origem, self.operador_origem)
        bem_dentro = self._criar_bem("550.000000000-0", self.ua_origem, self.operador_origem)
        movimentacao = self._criar_movimentacao(
            bem=bem_abaixo,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
            bens=[bem_abaixo, bem_dentro],
        )

        self._autenticar(self.gestor_origem)
        response = self.client.get(
            reverse("movimentacoes-list"),
            {
                "numero_patrimonial_inicial": "500.000000000-0",
                "numero_patrimonial_final": "600.000000000-0",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in self._lista_movimentacoes(response)}
        self.assertIn(movimentacao.id, ids)

    def test_filtro_por_intervalo_inclui_limites_inicial_e_final(self):
        movimentacao_inicial = self._criar_movimentacao(
            bem=self._criar_bem("500.000000000-0", self.ua_origem, self.operador_origem),
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )
        movimentacao_final = self._criar_movimentacao(
            bem=self._criar_bem("600.000000000-0", self.ua_origem, self.operador_origem),
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        self._autenticar(self.gestor_origem)
        response = self.client.get(
            reverse("movimentacoes-list"),
            {
                "numero_patrimonial_inicial": "500.000000000-0",
                "numero_patrimonial_final": "600.000000000-0",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in self._lista_movimentacoes(response)}
        self.assertIn(movimentacao_inicial.id, ids)
        self.assertIn(movimentacao_final.id, ids)

    def test_filtro_por_intervalo_com_apenas_limite_inicial(self):
        movimentacao_dentro = self._criar_movimentacao(
            bem=self._criar_bem("550.000000000-0", self.ua_origem, self.operador_origem),
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )
        movimentacao_fora = self._criar_movimentacao(
            bem=self._criar_bem("450.000000000-0", self.ua_origem, self.operador_origem),
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        self._autenticar(self.gestor_origem)
        response = self.client.get(
            reverse("movimentacoes-list"),
            {"numero_patrimonial_inicial": "500.000000000-0"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in self._lista_movimentacoes(response)}
        self.assertIn(movimentacao_dentro.id, ids)
        self.assertNotIn(movimentacao_fora.id, ids)

    def test_filtro_por_intervalo_com_apenas_limite_final(self):
        movimentacao_dentro = self._criar_movimentacao(
            bem=self._criar_bem("550.000000000-0", self.ua_origem, self.operador_origem),
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )
        movimentacao_fora = self._criar_movimentacao(
            bem=self._criar_bem("650.000000000-0", self.ua_origem, self.operador_origem),
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        self._autenticar(self.gestor_origem)
        response = self.client.get(
            reverse("movimentacoes-list"),
            {"numero_patrimonial_final": "600.000000000-0"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in self._lista_movimentacoes(response)}
        self.assertIn(movimentacao_dentro.id, ids)
        self.assertNotIn(movimentacao_fora.id, ids)

    def test_aprovar_e_rejeitar_exigem_itens_na_movimentacao(self):
        movimentacao = self._criar_movimentacao(
            bem=self.bem_api,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
            com_item=False,
        )

        self._autenticar(self.gestor_origem)
        aprovar = self.client.post(
            reverse("movimentacoes-aprovar", kwargs={"pk": movimentacao.pk})
        )
        rejeitar = self.client.post(
            reverse("movimentacoes-rejeitar", kwargs={"pk": movimentacao.pk})
        )

        self.assertEqual(aprovar.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(rejeitar.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("itens", aprovar.data)
        self.assertIn("itens", rejeitar.data)

    def test_listagem_filtra_por_intervalo_de_numero_patrimonial(self):
        movimentacao_intervalo = self._criar_movimentacao(
            bem=self.bem_api,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )

        self._autenticar(self.gestor_origem)
        response = self.client.get(
            reverse("movimentacoes-list"),
            {
                "numero_patrimonial_inicial": self.bem_api.numero_patrimonial,
                "numero_patrimonial_final": self.bem_api.numero_patrimonial,
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in self._lista_movimentacoes(response)}
        self.assertIn(movimentacao_intervalo.id, ids)
        self.assertNotIn(self.mov_visivel.id, ids)

    def test_resolver_itens_lote_retorna_bens_da_faixa(self):
        bens = [
            self._criar_bem(
                f"001.00000001{numero}-0",
                self.ua_origem,
                criado_por=self.operador_origem,
            )
            for numero in range(0, 3)
        ]
        self._autenticar(self.operador_origem)

        response = self.client.post(
            reverse("movimentacoes-resolver-itens-lote"),
            {
                "unidade_administrativa_origem": self.ua_origem.id,
                "faixas": [
                    {
                        "numero_patrimonial_de": bens[0].numero_patrimonial,
                        "numero_patrimonial_ate": bens[-1].numero_patrimonial,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in response.data["itens"]],
            [bem.id for bem in bens],
        )

    def test_resolver_itens_lote_aceita_bem_de_formato_antigo_sem_limite_final(self):
        bem = self._criar_bem(
            "01030001",
            self.ua_origem,
            criado_por=self.operador_origem,
            numero_formato_antigo=True,
        )
        self._autenticar(self.operador_origem)

        response = self.client.post(
            reverse("movimentacoes-resolver-itens-lote"),
            {
                "unidade_administrativa_origem": self.ua_origem.id,
                "faixas": [{"numero_patrimonial_de": bem.numero_patrimonial}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["itens"][0]["id"], bem.id)

    def test_resolver_itens_lote_aceita_um_unico_bem_com_de_igual_ate(self):
        bem = self._criar_bem(
            "01020001",
            self.ua_origem,
            criado_por=self.operador_origem,
            numero_formato_antigo=True,
        )
        self._autenticar(self.operador_origem)

        response = self.client.post(
            reverse("movimentacoes-resolver-itens-lote"),
            {
                "unidade_administrativa_origem": self.ua_origem.id,
                "faixas": [
                    {
                        "numero_patrimonial_de": bem.numero_patrimonial,
                        "numero_patrimonial_ate": bem.numero_patrimonial,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["itens"][0]["id"], bem.id)

    def test_resolver_itens_lote_retorna_bens_existentes_no_intervalo(self):
        inicio = self._criar_bem(
            "001.000000010-0",
            self.ua_origem,
            criado_por=self.operador_origem,
        )
        fim = self._criar_bem(
            "001.000000012-0",
            self.ua_origem,
            criado_por=self.operador_origem,
        )
        self._autenticar(self.operador_origem)

        response = self.client.post(
            reverse("movimentacoes-resolver-itens-lote"),
            {
                "unidade_administrativa_origem": self.ua_origem.id,
                "faixas": [
                    {
                        "numero_patrimonial_de": inicio.numero_patrimonial,
                        "numero_patrimonial_ate": fim.numero_patrimonial,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in response.data["itens"]],
            [inicio.id, fim.id],
        )

    def test_resolver_itens_lote_seleciona_todos_os_bens_aprovados_da_ua(self):
        bem_reprovado = self._criar_bem(
            "001.000000020-0",
            self.ua_origem,
            criado_por=self.operador_origem,
        )
        bem_reprovado.status = constants.NAO_APROVADO
        bem_reprovado.save()
        bem_bloqueado = self._criar_bem(
            "001.000000021-0",
            self.ua_origem,
            criado_por=self.operador_origem,
            bloqueado_conciliacao=True,
        )
        self._autenticar(self.operador_origem)

        response = self.client.post(
            reverse("movimentacoes-resolver-itens-lote"),
            {
                "unidade_administrativa_origem": self.ua_origem.id,
                "selecionar_todos": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data["itens"]}
        self.assertIn(self.bem_api.id, ids)
        self.assertNotIn(bem_reprovado.id, ids)
        self.assertNotIn(bem_bloqueado.id, ids)
        self.assertNotIn(self.bem_oculto.id, ids)
        self.assertNotIn(self.bem_visivel.id, ids)

    def test_resolver_itens_lote_ignora_bem_com_movimentacao_pendente(self):
        bem_movimentavel = self._criar_bem(
            "001.000000021-0",
            self.ua_origem,
            criado_por=self.operador_origem,
        )
        bem_pendente = self._criar_bem(
            "001.000000022-0",
            self.ua_origem,
            criado_por=self.operador_origem,
        )
        self._criar_movimentacao(
            bem=bem_pendente,
            ua_origem=self.ua_origem,
            ua_destino=self.ua_destino,
            solicitado_por=self.operador_origem,
        )
        bem_pendente.status = constants.APROVADO
        bem_pendente.save(update_fields=["status"])
        self._autenticar(self.operador_origem)

        response = self.client.post(
            reverse("movimentacoes-resolver-itens-lote"),
            {
                "unidade_administrativa_origem": self.ua_origem.id,
                "faixas": [
                    {
                        "numero_patrimonial_de": bem_movimentavel.numero_patrimonial,
                        "numero_patrimonial_ate": bem_pendente.numero_patrimonial,
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in response.data["itens"]],
            [bem_movimentavel.id],
        )

    def test_bens_movimentaveis_lista_apenas_bens_elegiveis(self):
        bem_bloqueado = self._criar_bem(
            "001.000000023-0",
            self.ua_origem,
            criado_por=self.operador_origem,
            bloqueado_conciliacao=True,
        )
        self._autenticar(self.operador_origem)

        response = self.client.get(
            reverse("movimentacoes-bens-movimentaveis"),
            {"unidade_administrativa_origem": self.ua_origem.id},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item["id"] for item in response.data}
        self.assertIn(self.bem_api.id, ids)
        self.assertNotIn(self.bem_visivel.id, ids)
        self.assertNotIn(bem_bloqueado.id, ids)

    def test_criacao_por_faixa_bloqueia_todos_os_bens_resolvidos(self):
        bens = [
            self._criar_bem(
                f"001.00000003{numero}-0",
                self.ua_origem,
                criado_por=self.operador_origem,
            )
            for numero in range(0, 2)
        ]
        self._autenticar(self.operador_origem)

        with patch("bem_patrimonial.models.envia_email_nova_solicitacao_movimentacao"):
            response = self.client.post(
                reverse("movimentacoes-list"),
                {
                    "unidade_administrativa_origem": self.ua_origem.id,
                    "unidade_administrativa_destino": self.ua_destino.id,
                    "faixas": [
                        {
                            "numero_patrimonial_de": bens[0].numero_patrimonial,
                            "numero_patrimonial_ate": bens[-1].numero_patrimonial,
                        }
                    ],
                },
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["total_itens"], len(bens))
        for bem in bens:
            bem.refresh_from_db()
            self.assertEqual(bem.status, constants.BLOQUEADO)

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
