from django.test import Client, TestCase
from django.urls import reverse

from bem_patrimonial import constants
from bem_patrimonial.models import (
    BemPatrimonial,
    TransferenciaBemPatrimonial,
    TransferenciaBensItem,
)
from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua, codigo_uo
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.constants import GRUPO_GESTOR_PATRIMONIO
from usuario.models import Usuario
from django.contrib.auth.models import Group


class NTBPMTestCase(TestCase):
    def setUp(self):
        self.uo_origem = criar_uo(codigo=codigo_uo(1, 16, 80), nome="SME", sigla="SME")
        self.ua_origem = criar_ua(
            uo=self.uo_origem,
            codigo=f"{self.uo_origem.codigo}.001",
            sigla="UA1",
            nome="Unidade 1",
        )
        self.uo_destino = criar_uo(
            codigo=codigo_uo(4, 40, 40),
            nome="Secretaria Externa",
            sigla="EXT",
        )
        self.ua_destino = criar_ua(
            uo=self.uo_destino,
            codigo=codigo_ua(4, 40, 40, 1),
            sigla="PC",
            nome="Ponto Central",
        )
        self.ua_destino_2 = criar_ua(
            uo=self.uo_destino,
            codigo=codigo_ua(4, 40, 40, 2),
            sigla="DST2",
            nome="Destino 2",
        )
        self.uo_terceira = criar_uo(
            codigo=codigo_uo(5, 50, 50),
            nome="Secretaria Terceira",
            sigla="TER",
        )
        self.ua_terceira = criar_ua(
            uo=self.uo_terceira,
            codigo=codigo_ua(5, 50, 50, 1),
            sigla="TER1",
            nome="Terceira 1",
        )

        grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        self.gestor = Usuario.objects.create_user(
            username="gestor_ntbpm",
            email="gestor.ntbpm@test.com",
            **auth_kwargs("senha123"),
            nome="Gestor NTBPM",
            is_staff=True,
            unidade_orcamentaria=self.uo_origem,
            unidade_administrativa=self.ua_origem,
        )
        self.gestor.groups.add(grupo_gestor)

        self.gestor_destino = Usuario.objects.create_user(
            username="gestor_destino_ntbpm",
            email="gestor.destino.ntbpm@test.com",
            **auth_kwargs("senha123"),
            nome="Gestor Destino NTBPM",
            is_staff=True,
            unidade_orcamentaria=self.uo_destino,
            unidade_administrativa=self.ua_destino_2,
        )
        self.gestor_destino.groups.add(grupo_gestor)

        self.gestor_terceiro = Usuario.objects.create_user(
            username="gestor_terceiro_ntbpm",
            email="gestor.terceiro.ntbpm@test.com",
            **auth_kwargs("senha123"),
            nome="Gestor Terceiro NTBPM",
            is_staff=True,
            unidade_orcamentaria=self.uo_terceira,
            unidade_administrativa=self.ua_terceira,
        )
        self.gestor_terceiro.groups.add(grupo_gestor)

        self.operador = Usuario.objects.create_user(
            username="operador_ntbpm",
            email="operador.ntbpm@test.com",
            **auth_kwargs("senha123"),
            nome="Operador NTBPM",
            is_staff=True,
            unidade_orcamentaria=self.uo_origem,
            unidade_administrativa=self.ua_origem,
        )

        self.bem = BemPatrimonial.objects.create(
            numero_patrimonial="001.000000050-0",
            nome="Bem NTBPM",
            descricao="Descrição",
            valor_unitario=100,
            marca="Marca",
            modelo="Modelo",
            numero_processo="PROC-BASE",
            status=constants.APROVADO,
            unidade_administrativa=self.ua_origem,
            criado_por=self.gestor,
        )
        self.transferencia = TransferenciaBemPatrimonial.objects.create(
            unidade_orcamentaria_origem=self.uo_origem,
            unidade_orcamentaria_destino=self.uo_destino,
            unidade_administrativa_destino=self.ua_destino,
            numero_processo="SEI-987654/2026",
            criado_por=self.gestor,
        )
        TransferenciaBensItem.objects.create(
            transferencia=self.transferencia,
            bem=self.bem,
        )
        self.transferencia.efetivar_transferencia(self.gestor)
        self.transferencia.refresh_from_db()

        self.client = Client()
        self.url = reverse(
            "download_documento_ntbpm",
            kwargs={"pk": self.transferencia.pk},
        )

    def test_numero_ntbpm_gerado_na_efetivacao(self):
        partes = self.transferencia.numero_ntbpm.split(".")

        self.assertEqual(len(partes), 4)
        self.assertEqual(len(partes[0]), 3)
        self.assertEqual(len(partes[1]), 3)
        self.assertEqual(len(partes[2]), 7)
        self.assertEqual(len(partes[3]), 4)

    def test_gestor_pode_baixar_documento_ntbpm(self):
        self.client.login(username="gestor_ntbpm", **auth_kwargs("senha123"))
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(
            f"NTBPM_{self.transferencia.numero_ntbpm.replace('.', '_')}.pdf",
            response["Content-Disposition"],
        )

    def test_gestor_destino_pode_baixar_documento_ntbpm(self):
        self.client.login(username="gestor_destino_ntbpm", **auth_kwargs("senha123"))
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_usuario_sem_grupo_gestor_nao_pode_baixar_documento_ntbpm(self):
        self.client.login(username="operador_ntbpm", **auth_kwargs("senha123"))
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    def test_gestor_sem_relacao_com_transferencia_nao_pode_baixar_documento_ntbpm(self):
        self.client.login(username="gestor_terceiro_ntbpm", **auth_kwargs("senha123"))
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 404)

    def test_conteudo_pdf_ntbpm_valido(self):
        self.client.login(username="gestor_ntbpm", **auth_kwargs("senha123"))
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content)
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertGreater(len(content), 1000)