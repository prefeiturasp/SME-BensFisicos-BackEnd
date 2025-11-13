from django.test import TestCase, Client
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal

from bem_patrimonial.models import (
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
    MovimentacaoBensItem,
)
from bem_patrimonial.cimbpm import (
    extrair_codigo_ua,
    formatar_moeda_brasileira,
    obter_bens_movimentacao,
    obter_nome_usuario,
)
from bem_patrimonial import constants
from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO


class CIMBPMTestBase(TestCase):

    def setUp(self):
        self.grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        self.grupo_operador, _ = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )

        self.ua_origem = UnidadeAdministrativa.objects.create(
            codigo="01.16.10.379",
            sigla="COSERV",
            nome="Coordenadoria de Contratos",
            status=UnidadeAdministrativa.ATIVA,
        )
        self.ua_destino = UnidadeAdministrativa.objects.create(
            codigo="01.16.10.408",
            sigla="ALMOXZE",
            nome="Almoxarifado Zeladoria",
            status=UnidadeAdministrativa.ATIVA,
        )

        self.operador = Usuario.objects.create_user(
            username="operador",
            nome="João Silva",
            rf="1234567",
            email="operador@exemplo.com",
            password="senha123",
            unidade_administrativa=self.ua_origem,
        )
        self.operador.groups.add(self.grupo_operador)

        self.gestor = Usuario.objects.create_user(
            username="gestor",
            nome="Maria Santos",
            rf="7654321",
            email="gestor@exemplo.com",
            password="senha123",
            unidade_administrativa=self.ua_destino,
        )
        self.gestor.groups.add(self.grupo_gestor)

    def criar_bem(self, **kwargs):
        defaults = {
            "numero_patrimonial": "001.053370965-3",
            "nome": "Armário",
            "descricao": "Armário de madeira",
            "valor_unitario": Decimal("2038.00"),
            "marca": "MarcaTeste",
            "modelo": "ModeloTeste",
            "numero_processo": "2024/001",
            "status": constants.APROVADO,
            "unidade_administrativa": self.ua_origem,
            "criado_por": self.operador,
        }
        defaults.update(kwargs)
        return BemPatrimonial.objects.create(**defaults)


class TestFuncoesAuxiliares(TestCase):

    def test_formatar_moeda_valores_diversos(self):
        casos = [
            (Decimal("0.00"), "R$ 0,00"),
            (Decimal("0.99"), "R$ 0,99"),
            (Decimal("1000"), "R$ 1.000,00"),
            (Decimal("1234.56"), "R$ 1.234,56"),
            (Decimal("123456.78"), "R$ 123.456,78"),
            (Decimal("1234567.89"), "R$ 1.234.567,89"),
        ]
        for valor, esperado in casos:
            with self.subTest(valor=valor):
                self.assertEqual(formatar_moeda_brasileira(valor), esperado)

    def test_extrair_codigo_ua_formatos_diversos(self):
        casos = [
            ("01.16.10.379", "379"),
            ("01.16.10.408", "408"),
            ("", "000"),
            ("ABC", "000"),
            ("0", "000"),
            ("@#$%379", "379"),
            ("01.16.10. 379", "379"),
            ("0000003", "003"),
            ("1", "001"),
            ("42", "042"),
            ("12345", "345"),
        ]
        for entrada, esperado in casos:
            with self.subTest(entrada=entrada):
                self.assertEqual(extrair_codigo_ua(entrada), esperado)

    def test_obter_nome_usuario_fallback(self):
        ua = UnidadeAdministrativa.objects.create(
            codigo="01.16.10.001", sigla="T", nome="Teste", status="A"
        )

        u1 = Usuario.objects.create_user(
            username="user1", nome="Nome Completo", unidade_administrativa=ua
        )
        self.assertEqual(obter_nome_usuario(u1), "Nome Completo")

        u2 = Usuario.objects.create_user(
            username="user2", nome="", unidade_administrativa=ua
        )
        self.assertEqual(obter_nome_usuario(u2), "user2")

        u3 = Usuario.objects.create_user(username="user3", unidade_administrativa=ua)
        u3.nome = None
        u3.save()
        self.assertEqual(obter_nome_usuario(u3), "user3")


class TestObterBensMovimentacao(CIMBPMTestBase):

    def test_bens_via_tabela_intermediaria(self):
        bem1 = self.criar_bem(numero_patrimonial="001.000000001-1")
        bem2 = self.criar_bem(numero_patrimonial="001.000000002-2")

        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem1,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )

        MovimentacaoBensItem.objects.create(movimentacao=mov, bem=bem1)
        MovimentacaoBensItem.objects.create(movimentacao=mov, bem=bem2)

        bens = obter_bens_movimentacao(mov)
        self.assertEqual(len(bens), 2)
        self.assertIn(bem1, bens)
        self.assertIn(bem2, bens)

    def test_fallback_bem_patrimonial(self):
        bem = self.criar_bem()
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )

        bens = obter_bens_movimentacao(mov)
        self.assertEqual(len(bens), 1)
        self.assertEqual(bens[0], bem)

    def test_ordenacao_por_numero_patrimonial(self):
        bem_z = self.criar_bem(numero_patrimonial="001.000000099-9")
        bem_a = self.criar_bem(numero_patrimonial="001.000000001-1")

        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem_a,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )

        MovimentacaoBensItem.objects.create(movimentacao=mov, bem=bem_z)
        MovimentacaoBensItem.objects.create(movimentacao=mov, bem=bem_a)

        bens = obter_bens_movimentacao(mov)
        self.assertEqual(bens[0], bem_a)
        self.assertEqual(bens[1], bem_z)


class TestGeracaoNumeroCIMBPM(CIMBPMTestBase):

    def test_formato_numero_cimbpm(self):
        bem = self.criar_bem()
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )
        mov.refresh_from_db()

        partes = mov.numero_cimbpm.split(".")
        self.assertEqual(len(partes), 4)
        self.assertEqual(partes[0], "379")  # Código origem
        self.assertEqual(partes[1], "408")  # Código destino
        self.assertEqual(len(partes[2]), 7)  # Sequencial
        self.assertEqual(len(partes[3]), 4)  # Ano

    def test_geracao_sequencial(self):
        bem1 = self.criar_bem(numero_patrimonial="001.000000001-1")
        bem2 = self.criar_bem(numero_patrimonial="001.000000002-2")

        mov1 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem1,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )
        mov1.refresh_from_db()

        mov2 = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem2,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )
        mov2.refresh_from_db()

        ano_atual = timezone.now().year
        self.assertEqual(mov1.numero_cimbpm, f"379.408.0000001.{ano_atual}")
        self.assertEqual(mov2.numero_cimbpm, f"379.408.0000002.{ano_atual}")

    def test_sequencial_reinicia_ao_mudar_ano(self):
        from unittest.mock import patch
        from datetime import datetime

        bem1 = self.criar_bem(numero_patrimonial="001.000000001-1")
        bem2 = self.criar_bem(numero_patrimonial="001.000000002-2")

        data_2024 = datetime(
            2024, 12, 31, 23, 59, 59, tzinfo=timezone.get_current_timezone()
        )
        with patch("django.utils.timezone.now", return_value=data_2024):
            mov_2024 = MovimentacaoBemPatrimonial.objects.create(
                bem_patrimonial=bem1,
                unidade_administrativa_origem=self.ua_origem,
                unidade_administrativa_destino=self.ua_destino,
                solicitado_por=self.operador,
                status=constants.ENVIADA,
            )
            mov_2024.refresh_from_db()

        self.assertEqual(mov_2024.numero_cimbpm, "379.408.0000001.2024")

        data_2025 = datetime(
            2025, 1, 1, 0, 0, 0, tzinfo=timezone.get_current_timezone()
        )
        with patch("django.utils.timezone.now", return_value=data_2025):
            mov_2025 = MovimentacaoBemPatrimonial.objects.create(
                bem_patrimonial=bem2,
                unidade_administrativa_origem=self.ua_origem,
                unidade_administrativa_destino=self.ua_destino,
                solicitado_por=self.operador,
                status=constants.ENVIADA,
            )
            mov_2025.refresh_from_db()

        self.assertEqual(mov_2025.numero_cimbpm, "379.408.0000001.2025")


class TestGeracaoDocumentoPDF(CIMBPMTestBase):

    def test_geracao_automatica_pdf(self):
        bem = self.criar_bem()
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )
        mov.refresh_from_db()

        self.assertTrue(mov.documento_cimbpm)
        self.assertIn("CIMBPM_", mov.documento_cimbpm.name)
        self.assertTrue(mov.documento_cimbpm.name.endswith(".pdf"))

    def test_validacao_conteudo_pdf(self):
        bem = self.criar_bem()
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )
        mov.refresh_from_db()

        pdf_file = mov.documento_cimbpm.open("rb")
        pdf_content = pdf_file.read()
        pdf_file.close()

        self.assertTrue(pdf_content.startswith(b"%PDF"))
        self.assertGreater(len(pdf_content), 1000)

    def test_atualizacao_pdf_apos_aprovacao(self):
        bem = self.criar_bem()
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )
        mov.refresh_from_db()
        numero_original = mov.numero_cimbpm

        mov.aprovar_solicitacao(self.gestor)
        mov.refresh_from_db()

        self.assertEqual(mov.numero_cimbpm, numero_original)
        self.assertTrue(mov.documento_cimbpm)
        self.assertEqual(mov.status, constants.ACEITA)

    def test_pdf_multiplos_bens(self):
        bens = [
            self.criar_bem(
                numero_patrimonial=f"001.{str(i).zfill(9)}-{i % 10}",
                nome=f"Item {i}",
                descricao=f"Descrição do item {i}",
            )
            for i in range(1, 101)
        ]

        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bens[0],
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.AGUARDANDO_APROVACAO,
        )

        for bem in bens:
            MovimentacaoBensItem.objects.create(movimentacao=mov, bem=bem)

        mov.regenerar_documento_cimbpm(force=True)
        mov.refresh_from_db()

        self.assertTrue(mov.documento_cimbpm)
        self.assertTrue(mov.documento_existe())


class TestEdgeCasesPDF(CIMBPMTestBase):

    def test_bem_sem_numero_patrimonial(self):
        bem = self.criar_bem(numero_patrimonial=None)
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )
        mov.refresh_from_db()

        self.assertTrue(mov.documento_existe())

    def test_bem_com_descricao_vazia(self):
        bem = self.criar_bem(descricao="")
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )
        mov.refresh_from_db()

        self.assertTrue(mov.documento_existe())

    def test_bem_com_valor_zero(self):
        bem = self.criar_bem(valor_unitario=Decimal("0.00"))
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )
        mov.refresh_from_db()

        self.assertTrue(mov.documento_existe())

    def test_usuario_sem_rf(self):
        usuario_sem_rf = Usuario.objects.create_user(
            username="sem_rf",
            nome="Usuário Sem RF",
            rf=None,
            unidade_administrativa=self.ua_origem,
        )
        usuario_sem_rf.groups.add(self.grupo_operador)

        bem = self.criar_bem(criado_por=usuario_sem_rf)
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=usuario_sem_rf,
            status=constants.ENVIADA,
        )
        mov.refresh_from_db()

        self.assertTrue(mov.documento_existe())

    def test_pdf_com_logo_inexistente(self):
        import os
        from unittest.mock import patch

        bem = self.criar_bem()
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )

        with patch("os.path.exists", return_value=False):
            mov.refresh_from_db()
            self.assertTrue(mov.documento_existe())


class TestRegeneracaoDocumento(CIMBPMTestBase):

    def test_metodo_documento_existe(self):
        bem = self.criar_bem()
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )
        mov.refresh_from_db()

        self.assertTrue(mov.documento_existe())

        import os

        if mov.documento_cimbpm:
            caminho = mov.documento_cimbpm.path
            if os.path.exists(caminho):
                os.remove(caminho)

        self.assertFalse(mov.documento_existe())

    def test_regenerar_documento_force(self):
        bem = self.criar_bem()
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )
        mov.refresh_from_db()

        self.assertFalse(mov.regenerar_documento_cimbpm(force=False))

        self.assertTrue(mov.regenerar_documento_cimbpm(force=True))

    def test_regeneracao_automatica_via_admin(self):
        from bem_patrimonial.admins.movimentacao_bem_patrimonial import (
            MovimentacaoBemPatrimonialAdmin,
        )
        from django.contrib.admin.sites import AdminSite

        bem = self.criar_bem()
        mov = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )
        mov.refresh_from_db()

        import os

        if mov.documento_cimbpm:
            if os.path.exists(mov.documento_cimbpm.path):
                os.remove(mov.documento_cimbpm.path)

        self.assertFalse(mov.documento_existe())

        admin = MovimentacaoBemPatrimonialAdmin(MovimentacaoBemPatrimonial, AdminSite())
        link_html = admin.get_documento_cimbpm_link(mov)

        self.assertIn("href=", link_html)
        self.assertIn("Baixar Documento CIMBPM", link_html)

        mov.refresh_from_db()
        self.assertTrue(mov.documento_existe())


class TestSegurancaDownload(CIMBPMTestBase):

    def setUp(self):
        super().setUp()

        self.ua_terceira = UnidadeAdministrativa.objects.create(
            codigo="01.16.10.500",
            sigla="OUTRA",
            nome="Outra Unidade",
            status=UnidadeAdministrativa.ATIVA,
        )

        self.operador_terceiro = Usuario.objects.create_user(
            username="operador_terceiro",
            nome="José Costa",
            rf="9999999",
            password="senha123",
            unidade_administrativa=self.ua_terceira,
        )
        self.operador_terceiro.groups.add(self.grupo_operador)

        self.operador_destino = Usuario.objects.create_user(
            username="operador_destino",
            nome="Pedro Alves",
            rf="5555555",
            password="senha123",
            unidade_administrativa=self.ua_destino,
        )
        self.operador_destino.groups.add(self.grupo_operador)

        bem = self.criar_bem()
        self.movimentacao = MovimentacaoBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            unidade_administrativa_origem=self.ua_origem,
            unidade_administrativa_destino=self.ua_destino,
            solicitado_por=self.operador,
            status=constants.ENVIADA,
        )
        self.movimentacao.refresh_from_db()

        self.client = Client()
        self.url = reverse(
            "download_documento_cimbpm", kwargs={"pk": self.movimentacao.pk}
        )

    def test_usuario_nao_autenticado_redirecionado(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_operador_origem_pode_baixar(self):
        self.client.login(username="operador", password="senha123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_operador_destino_pode_baixar(self):
        self.client.login(username="operador_destino", password="senha123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_operador_sem_relacao_nao_pode_baixar(self):
        self.client.login(username="operador_terceiro", password="senha123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_gestor_pode_baixar_qualquer_documento(self):
        self.client.login(username="gestor", password="senha123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_documento_inexistente_retorna_404(self):
        self.client.login(username="gestor", password="senha123")
        url = reverse("download_documento_cimbpm", kwargs={"pk": 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_filename_correto_download(self):
        self.client.login(username="gestor", password="senha123")
        response = self.client.get(self.url)

        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(
            f"CIMBPM_{self.movimentacao.numero_cimbpm.replace('.', '_')}.pdf",
            response["Content-Disposition"],
        )
