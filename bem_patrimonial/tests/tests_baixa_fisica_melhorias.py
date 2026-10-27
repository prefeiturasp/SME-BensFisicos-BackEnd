"""Melhorias fluxo Baixa Física: edição Aceita, Laudado->Baixa Física, laudo com Nome."""
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status as drf_status
from rest_framework.test import APIClient

from dados_comuns.tests.auth_test_utils import auth_kwargs
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from reportlab.lib.styles import getSampleStyleSheet

from bem_patrimonial import constants
from bem_patrimonial.admins.baixa_fisica_bem_patrimonial import (
    BaixaFisicaBemPatrimonialAdmin,
    BaixaFisicaBensItemInline,
)
from bem_patrimonial.laudo_avaliacao import gerar_pdf_laudo_avaliacao, _criar_tabela_bens
from bem_patrimonial.models import (
    BaixaFisicaBemPatrimonial,
    BaixaFisicaBensItem,
    BemPatrimonial,
    NBBPM,
)
from bem_patrimonial.services.nbbpm_numero import criar_nbbpm_com_retry


def _criar_usuario(username, uo, ua, grupos=None, **kw):
    u = Usuario.objects.create_user(
        username=username, email=f"{username}@t.com", **auth_kwargs("x"),
        unidade_administrativa=ua, unidade_orcamentaria=uo,
        is_staff=True, **kw,
    )
    for g in (grupos or []):
        grp, _ = Group.objects.get_or_create(name=g)
        u.groups.add(grp)
    return u


def _criar_bem(ua, user, numero="000.000000001-0", st=constants.APROVADO, nome="Bem X", desc="Desc X"):
    return BemPatrimonial.objects.create(
        nome=nome, descricao=desc, valor_unitario=100,
        marca="M", modelo="Md", numero_patrimonial=numero,
        unidade_administrativa=ua, criado_por=user, status=st,
    )


def _criar_baixa(ua, user, st=constants.AGUARDANDO_ENVIO, processo="PROC-BX"):
    return BaixaFisicaBemPatrimonial.objects.create(
        unidade_administrativa_origem=ua, numero_processo_baixa=processo,
        status=st, criado_por=user, data_baixa=timezone.localdate(),
    )


class BaseBaixa(TestCase):
    def setUp(self):
        self.uo = criar_uo(codigo="100", nome="UO", sigla="UOT")
        self.ua = criar_ua(uo=self.uo, codigo="001", nome="UA", sigla="UAT")
        self.gestor = _criar_usuario("gest_mel", self.uo, self.ua, [GRUPO_GESTOR_PATRIMONIO])
        self.oper = _criar_usuario("oper_mel", self.uo, self.ua, [GRUPO_OPERADOR_INVENTARIO])
        self.bem = _criar_bem(self.ua, self.oper, nome="Cadeira", desc="Cadeira giratória")
        self.bem2 = _criar_bem(self.ua, self.oper, numero="000.000000002-0", nome="Mesa", desc="Mesa madeira")
        self.client = APIClient()


class AprovacaoLaudadoNBBPMTestCase(BaseBaixa):
    def test_aprovacao_marca_laudado_para_baixa(self):
        baixa = _criar_baixa(self.ua, self.oper, st=constants.SOLICITADA)
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        baixa.aprovar(self.gestor, numero_processo_baixa="6016.2025/0117371-7")
        self.bem.refresh_from_db()
        self.assertEqual(baixa.status, constants.ACEITA)
        self.assertEqual(self.bem.status, constants.LAUDADO_PARA_BAIXA)
        self.assertEqual(self.bem.numero_processo, "6016.2025/0117371-7")

    def test_nbbpm_evolui_laudado_para_baixa_fisica(self):
        baixa = _criar_baixa(self.ua, self.oper, st=constants.SOLICITADA)
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        baixa.aprovar(self.gestor, numero_processo_baixa="6016.2025/0117371-7")
        nbbpm = criar_nbbpm_com_retry(
            baixas=[baixa], numero_processo_baixa="6016.2025/0117371-7",
            data_autorizacao=timezone.localdate(), responsavel="G",
            criado_por=self.gestor,
        )
        self.assertTrue(nbbpm.numero.startswith("001."))
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, constants.BAIXA_FISICA)

    def test_criacao_marca_aguardando_aprovacao_e_retorna_201(self):
        self.client.force_authenticate(user=self.oper)
        resp = self.client.post(
            reverse("baixas-fisicas-list"),
            {"unidade_administrativa_origem": self.ua.id,
             "itens": [{"bem": self.bem.id}],
             "data_baixa": str(timezone.localdate())},
            format="json",
        )
        self.assertEqual(resp.status_code, drf_status.HTTP_201_CREATED)
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)

    def test_envio_marca_aguardando_e_retorna_200(self):
        baixa = _criar_baixa(self.ua, self.oper)
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        self.client.force_authenticate(user=self.oper)
        resp = self.client.post(reverse("baixas-fisicas-enviar-solicitacao", kwargs={"pk": baixa.pk}))
        self.assertEqual(resp.status_code, drf_status.HTTP_200_OK)
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, constants.BAIXA_FISICA_AGUARDANDO_APROVACAO)


class EdicaoAceitaAPITestCase(BaseBaixa):
    def _baixa_aceita(self):
        baixa = _criar_baixa(self.ua, self.oper, st=constants.SOLICITADA,
                             processo="6016.2025/0117371-7")
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        self.bem.status = constants.BAIXA_FISICA_AGUARDANDO_APROVACAO
        self.bem.save(update_fields=["status"])
        baixa.aprovar(self.gestor, numero_processo_baixa="6016.2025/0117371-7")
        baixa.refresh_from_db()
        self.bem.refresh_from_db()
        return baixa

    def test_gestor_adiciona_e_remove_em_aceita_200(self):
        baixa = self._baixa_aceita()
        self.assertEqual(self.bem.status, constants.LAUDADO_PARA_BAIXA)
        self.client.force_authenticate(user=self.gestor)
        resp = self.client.patch(
            reverse("baixas-fisicas-detail", kwargs={"pk": baixa.pk}),
            {"itens": [{"bem": self.bem2.id}]}, format="json",
        )
        self.assertEqual(resp.status_code, drf_status.HTTP_200_OK)
        self.bem.refresh_from_db()
        self.bem2.refresh_from_db()
        self.assertEqual(self.bem.status, constants.APROVADO)
        self.assertEqual(self.bem.numero_processo, "")
        self.assertEqual(self.bem.localizacao, "")
        self.assertEqual(self.bem2.status, constants.LAUDADO_PARA_BAIXA)
        self.assertEqual(self.bem2.numero_processo, "6016.2025/0117371-7")

    def test_edicao_aceita_bloqueada_com_nbbpm_400(self):
        baixa = self._baixa_aceita()
        nbbpm = NBBPM.objects.create(
            numero="001.0000001/2026", numero_processo_baixa="6016.2025/0117371-7",
            data_autorizacao=timezone.localdate(), responsavel="G",
            criado_por=self.gestor)
        nbbpm.baixas.set([baixa])
        self.client.force_authenticate(user=self.gestor)
        resp = self.client.patch(
            reverse("baixas-fisicas-detail", kwargs={"pk": baixa.pk}),
            {"itens": [{"bem": self.bem.id}]}, format="json",
        )
        self.assertEqual(resp.status_code, drf_status.HTTP_400_BAD_REQUEST)

    def test_operador_nao_edita_aceita_403(self):
        baixa = self._baixa_aceita()
        self.client.force_authenticate(user=self.oper)
        resp = self.client.patch(
            reverse("baixas-fisicas-detail", kwargs={"pk": baixa.pk}),
            {"itens": [{"bem": self.bem.id}]}, format="json",
        )
        self.assertEqual(resp.status_code, drf_status.HTTP_403_FORBIDDEN)

    def test_edicao_aceita_unidade_divergente_400(self):
        baixa = self._baixa_aceita()
        ua2 = criar_ua(uo=self.uo, codigo="002", nome="UA2", sigla="UA2")
        bem_outra = _criar_bem(ua2, self.oper, numero="000.000000009-0")
        self.client.force_authenticate(user=self.gestor)
        resp = self.client.patch(
            reverse("baixas-fisicas-detail", kwargs={"pk": baixa.pk}),
            {"itens": [{"bem": bem_outra.id}]}, format="json",
        )
        self.assertEqual(resp.status_code, drf_status.HTTP_400_BAD_REQUEST)

    def test_formato_processo_invalido_aprovar_400(self):
        baixa = _criar_baixa(self.ua, self.oper, st=constants.SOLICITADA)
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        self.client.force_authenticate(user=self.gestor)
        resp = self.client.post(
            reverse("baixas-fisicas-aprovar", kwargs={"pk": baixa.pk}),
            {"numero_processo_baixa": "RUIM"}, format="json",
        )
        self.assertEqual(resp.status_code, drf_status.HTTP_400_BAD_REQUEST)


class EdicaoAceitaAdminTestCase(BaseBaixa):
    def _req(self, user):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.backends.db import SessionStore
        rf = RequestFactory()
        req = rf.post("/admin/")
        req.user = user
        req.session = SessionStore()
        req.session.create()
        req._messages = FallbackStorage(req)
        return req

    def test_admin_gestor_edita_aceita_adiciona_remove(self):
        admin = BaixaFisicaBemPatrimonialAdmin(BaixaFisicaBemPatrimonial, AdminSite())
        baixa = _criar_baixa(self.ua, self.oper, st=constants.SOLICITADA,
                             processo="6016.2025/0117371-7")
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        self.bem.status = constants.BAIXA_FISICA_AGUARDANDO_APROVACAO
        self.bem.save(update_fields=["status"])
        baixa.aprovar(self.gestor, numero_processo_baixa="6016.2025/0117371-7")
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, constants.LAUDADO_PARA_BAIXA)
        # Simula remoção via métodos internos do admin.
        item = baixa.itens.select_related("bem").get(bem_id=self.bem.id)
        req = self._req(self.gestor)
        self.assertTrue(
            admin._baixa_permite_edicao_via_save_related(req, baixa))
        # Reverte removido -> Aprovado.
        admin._reverter_bens_removidos(
            type("FS", (), {"deleted_objects": [item]})(),
            constants.LAUDADO_PARA_BAIXA)
        self.bem.refresh_from_db()
        self.assertEqual(self.bem.status, constants.APROVADO)
        self.assertEqual(self.bem.numero_processo, "")
        self.assertEqual(self.bem.localizacao, "")
        # Ativa novo -> Laudado com processo propagado.
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem2)
        novo_item = baixa.itens.select_related("bem").get(bem_id=self.bem2.id)
        admin._ativar_bens_novos(
            type("FS", (), {"new_objects": [novo_item]})(),
            constants.LAUDADO_PARA_BAIXA, baixa)
        self.bem2.refresh_from_db()
        self.assertEqual(self.bem2.status, constants.LAUDADO_PARA_BAIXA)
        self.assertEqual(self.bem2.numero_processo, "6016.2025/0117371-7")

    def test_admin_bloqueia_edicao_aceita_com_nbbpm(self):
        inline = BaixaFisicaBensItemInline(BaixaFisicaBemPatrimonial, AdminSite())
        baixa = _criar_baixa(self.ua, self.oper, st=constants.ACEITA,
                             processo="6016.2025/0117371-7")
        nbbpm = NBBPM.objects.create(
            numero="001.0000009/2026", numero_processo_baixa="6016.2025/0117371-7",
            data_autorizacao=timezone.localdate(), responsavel="G",
            criado_por=self.gestor)
        nbbpm.baixas.set([baixa])
        req = self._req(self.gestor)
        self.assertFalse(inline._baixa_permite_edicao_itens(req, baixa))


class LaudoNomeBemTestCase(BaseBaixa):
    def test_laudo_contem_nome_do_bem_pdf_integro(self):
        baixa = _criar_baixa(self.ua, self.oper, st=constants.SOLICITADA,
                             processo="6016.2025/0117371-7")
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        self.bem.status = constants.BAIXA_FISICA_AGUARDANDO_APROVACAO
        self.bem.save(update_fields=["status"])
        baixa.aprovar(self.gestor, numero_processo_baixa="6016.2025/0117371-7")
        tabela = _criar_tabela_bens(baixa, getSampleStyleSheet())[0]
        # 3 colunas: patrimonial, nome, descrição; cabeçalho repete.
        self.assertEqual(len(tabela._argW), 3)
        self.assertEqual(tabela.repeatRows, 1)
        # Confere que nomes/descrições estão no conteúdo da tabela.
        self.assertIn(self.bem.nome.upper(), str(tabela._cellvalues).upper())
        buf = gerar_pdf_laudo_avaliacao(baixa)
        dados = buf.getvalue()
        self.assertTrue(dados.startswith(b"%PDF"))
        self.assertGreater(len(dados), 1000)

    def test_laudo_so_aceita_400_quando_nao_aceita(self):
        baixa = _criar_baixa(self.ua, self.oper, st=constants.AGUARDANDO_ENVIO)
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        self.client.force_authenticate(user=self.gestor)
        resp = self.client.get(reverse("baixas-fisicas-gerar-laudo", kwargs={"pk": baixa.pk}))
        self.assertEqual(resp.status_code, drf_status.HTTP_400_BAD_REQUEST)

    def test_laudo_aceita_retorna_200_pdf(self):
        baixa = _criar_baixa(self.ua, self.oper, st=constants.SOLICITADA,
                             processo="6016.2025/0117371-7")
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        self.bem.status = constants.BAIXA_FISICA_AGUARDANDO_APROVACAO
        self.bem.save(update_fields=["status"])
        baixa.aprovar(self.gestor, numero_processo_baixa="6016.2025/0117371-7")
        self.client.force_authenticate(user=self.gestor)
        resp = self.client.get(reverse("baixas-fisicas-gerar-laudo", kwargs={"pk": baixa.pk}))
        self.assertEqual(resp.status_code, drf_status.HTTP_200_OK)
        self.assertEqual(resp["Content-Type"], "application/pdf")
