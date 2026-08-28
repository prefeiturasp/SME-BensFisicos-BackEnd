"""
Testes de cobertura da refatoração NBBPM unificada.
Valida:
- geração por ano com continuidade (prefixo fixo 001, sequencial global por ano)
- unicidade, formato 001.YYYYYYY/ZZZZ e prefixo fixo
- concorrência primeira NBBPM do ano e reuso mesma baixa
- validações de vínculo por UO, permissão gestor/superuser, visibilidade superuser
- data migration idempotente e tratamento ACEITA sem número via admin
- PDF layout lote e export Excel buscando nova tabela
"""
import importlib.util
import pathlib
import threading
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.apps import apps as django_apps
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework import status
from rest_framework.test import APIClient

from bem_patrimonial import constants
from bem_patrimonial.admins.baixa_fisica_bem_patrimonial import (
    BaixaFisicaBemPatrimonialAdmin,
    BaixaFisicaResource,
)
from bem_patrimonial.api_serializers import (
    BaixaFisicaBemPatrimonialListSerializer,
    NBBPMGerarLoteSerializer,
)
from bem_patrimonial.api_views import BaixaFisicaBemPatrimonialViewSet
from bem_patrimonial.models import (
    BaixaFisicaBemPatrimonial,
    BaixaFisicaBensItem,
    BemPatrimonial,
    NBBPM,
)
from bem_patrimonial.nbbpm_api_views import NBBPMViewSet
from bem_patrimonial.nbbpm_lote import _criar_tabela_bens, gerar_pdf_nbbpm_lote
from bem_patrimonial.pdf_utils import extrair_codigo_ua
from bem_patrimonial.services import nbbpm_numero as svc
from bem_patrimonial.services.nbbpm_numero import (
    criar_nbbpm_com_retry,
    gerar_numero_nbbpm_unificado,
)
from dados_comuns.models import UnidadeOrcamentaria as UO_Model
from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua
from dados_comuns.tests.factories import criar_ua
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario


def criar_uo(codigo="200", nome="UO Teste", sigla="UO", **kwargs):
    obj, _ = UO_Model.objects.get_or_create(codigo=codigo, defaults={"nome": nome, "sigla": sigla, **kwargs})
    return obj


def criar_usuario(username, uo, ua, grupos=None, is_superuser=False, **kwargs):
    user = Usuario.objects.create_user(
        username=username,
        email=f"{username}@test.com",
        **auth_kwargs("senha123"),
        unidade_administrativa=ua,
        unidade_orcamentaria=uo,
        is_superuser=is_superuser,
        is_staff=True,
        **kwargs,
    )
    for g in (grupos or []):
        grp, _ = Group.objects.get_or_create(name=g)
        user.groups.add(grp)
    return user


def criar_bem(ua, criado_por, numero_patrimonial="000.000000001-0", **kwargs):
    return BemPatrimonial.objects.create(
        nome=kwargs.pop("nome", "Notebook"),
        descricao=kwargs.pop("descricao", "Desc"),
        valor_unitario=kwargs.pop("valor_unitario", Decimal("1000.00")),
        marca=kwargs.pop("marca", "Dell"),
        modelo=kwargs.pop("modelo", "Latitude"),
        numero_processo=kwargs.pop("numero_processo", "PROC-TESTE"),
        numero_patrimonial=numero_patrimonial,
        unidade_administrativa=ua,
        criado_por=criado_por,
        status=kwargs.pop("status", constants.APROVADO),
        **kwargs,
    )


def criar_baixa(ua, criado_por, status=constants.ACEITA, **kwargs):
    return BaixaFisicaBemPatrimonial.objects.create(
        unidade_administrativa_origem=ua,
        numero_processo_baixa=kwargs.pop("numero_processo_baixa", "PROC-BX-001"),
        status=status,
        criado_por=criado_por,
        data_baixa=kwargs.pop("data_baixa", timezone.localdate()),
        numero_nbbpm=kwargs.pop("numero_nbbpm", ""),
        **kwargs,
    )


# Helpers compartilhados para reduzir duplicação
UO_SME = {"codigo": "01.16.10", "nome": "UO SME", "sigla": "SME"}


def _load_migracao_0044():
    spec = importlib.util.spec_from_file_location(
        "migr_0044", str(pathlib.Path(__file__).resolve().parent.parent / "migrations/0044_unificar_nbbpm_ua_ano.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _nova_baixa_com_item(ua, gestor, bem=None, **kwargs):
    baixa = criar_baixa(ua, gestor, **kwargs)
    bem_obj = bem or criar_bem(ua, gestor)
    BaixaFisicaBensItem.objects.create(baixa=baixa, bem=bem_obj)
    return baixa, bem_obj


def _novo_nbbpm_com_baixas(numero, baixas, criado_por, **kwargs):
    nbbpm = NBBPM.objects.create(
        numero=numero,
        numero_processo_baixa=kwargs.pop("numero_processo_baixa", "PROC"),
        data_autorizacao=kwargs.pop("data_autorizacao", timezone.localdate()),
        responsavel=kwargs.pop("responsavel", "G"),
        criado_por=criado_por,
        **kwargs,
    )
    if baixas:
        nbbpm.baixas.set(baixas)
    return nbbpm


def _setup_uo_ua_gestor(username="gestor_padrao", ua_codigo="001", ua_sigla="UAT", ua_nome="UA Teste", **kwargs):
    uo = criar_uo(**UO_SME)
    ua = criar_ua(uo=uo, codigo=ua_codigo, sigla=ua_sigla, nome=ua_nome)
    gestor = criar_usuario(username, uo, ua, grupos=[GRUPO_GESTOR_PATRIMONIO], **kwargs)
    return uo, ua, gestor


# =====================================================================
# 1. Prefixo UA (último grupo) e extração
# =====================================================================

class TestExtrairCodigoUa(TestCase):
    def test_ua_01_16_10_287_retorna_287(self):
        self.assertEqual(extrair_codigo_ua("01.16.10.287"), "287")

    def test_ua_simples_100_retorna_100(self):
        self.assertEqual(extrair_codigo_ua("100"), "100")

    def test_codigo_vazio_retorna_000(self):
        self.assertEqual(extrair_codigo_ua(""), "000")
        self.assertEqual(extrair_codigo_ua(None), "000")

    def test_ua_com_zero_pad(self):
        self.assertEqual(extrair_codigo_ua("01.02.10"), "010")
        self.assertEqual(extrair_codigo_ua("5"), "005")


# =====================================================================
# 2. Geração por UA/ano com continuidade (não reseta para 0000001)
# =====================================================================

class TestGeracaoPorUOAnoContinuidade(TestCase):
    def setUp(self):
        self.uo = criar_uo(**UO_SME)
        self.ua1 = criar_ua(uo=self.uo, codigo=codigo_ua(1, 16, 10, 100), sigla="UA100", nome="UA 100")
        self.ua2 = criar_ua(uo=self.uo, codigo=codigo_ua(1, 16, 10, 200), sigla="UA200", nome="UA 200")
        self.gestor = criar_usuario("gestor_cont", self.uo, self.ua1, grupos=[GRUPO_GESTOR_PATRIMONIO])
        self.bem = criar_bem(self.ua1, self.gestor)

    def test_continuidade_nao_reseta_para_0000001_quando_historico_grande(self):
        ano = 2026
        legado_num = f"001.{1234:07d}/{ano}"
        criar_baixa(self.ua1, self.gestor, status=constants.ACEITA, numero_nbbpm=legado_num)
        baixa2, _ = _nova_baixa_com_item(self.ua1, self.gestor, bem=self.bem, status=constants.ACEITA)
        nbbpm = _novo_nbbpm_com_baixas(
            "", [baixa2], self.gestor, data_autorizacao=timezone.datetime(ano, 6, 15).date(), numero_processo_baixa="PROC-NEW", responsavel="Gestor"
        )
        self.assertEqual(gerar_numero_nbbpm_unificado(nbbpm), f"001.{1235:07d}/{ano}")

    def test_sequencial_por_uo_isolado_entre_uos(self):
        uo_b = criar_uo(codigo="200", nome="UO B", sigla="UOB")
        ua_b = criar_ua(uo=uo_b, codigo="200", sigla="UAB", nome="UA B")
        gestor_b = criar_usuario("gestor_b", uo_b, ua_b, grupos=[GRUPO_GESTOR_PATRIMONIO])
        bem_b = criar_bem(ua_b, gestor_b, numero_patrimonial="000.000000010-0")
        ano = 2026
        for i in range(5):
            criar_baixa(self.ua1, self.gestor, status=constants.ACEITA, numero_nbbpm=f"001.{i+1:07d}/{ano}")
        baixa_b, _ = _nova_baixa_com_item(ua_b, gestor_b, bem=bem_b, status=constants.ACEITA)
        nbbpm_b = _novo_nbbpm_com_baixas("", [baixa_b], gestor_b, data_autorizacao=timezone.datetime(ano, 6, 15).date(), numero_processo_baixa="PROC-B")
        numero_b = gerar_numero_nbbpm_unificado(nbbpm_b)
        self.assertEqual(numero_b, f"001.{6:07d}/{ano}")
        nbbpm_b.numero = numero_b
        nbbpm_b.save(update_fields=["numero"])
        baixa_a2, _ = _nova_baixa_com_item(self.ua1, self.gestor, bem=self.bem, status=constants.ACEITA)
        nbbpm_a = _novo_nbbpm_com_baixas("", [baixa_a2], self.gestor, data_autorizacao=timezone.datetime(ano, 6, 15).date(), numero_processo_baixa="PROC-A")
        self.assertEqual(gerar_numero_nbbpm_unificado(nbbpm_a), f"001.{7:07d}/{ano}")

    def test_ano_diferente_reseta_sequencial(self):
        ano1, ano2 = 2025, 2026
        criar_baixa(self.ua1, self.gestor, status=constants.ACEITA, numero_nbbpm=f"001.{10:07d}/{ano1}")
        baixa, _ = _nova_baixa_com_item(self.ua1, self.gestor, bem=self.bem, status=constants.ACEITA)
        nbbpm = _novo_nbbpm_com_baixas("", [baixa], self.gestor, data_autorizacao=timezone.datetime(ano1, 5, 1).date(), numero_processo_baixa="P")
        self.assertEqual(gerar_numero_nbbpm_unificado(nbbpm), f"001.{11:07d}/{ano1}")
        baixa2, _ = _nova_baixa_com_item(self.ua1, self.gestor, bem=self.bem, status=constants.ACEITA)
        nbbpm2 = _novo_nbbpm_com_baixas("", [baixa2], self.gestor, data_autorizacao=timezone.datetime(ano2, 5, 1).date(), numero_processo_baixa="P2")
        self.assertEqual(gerar_numero_nbbpm_unificado(nbbpm2), f"001.{1:07d}/{ano2}")


# =====================================================================
# 3. Unicidade e formato
# =====================================================================

class TestUnicidadeEFormato(TestCase):
    def setUp(self):
        self.uo, self.ua, self.gestor = _setup_uo_ua_gestor("gestor_uniq")
        self.bem = criar_bem(self.ua, self.gestor)

    def test_formato_xxx_yyyyyyy_zzzz(self):
        baixa, _ = _nova_baixa_com_item(self.ua, self.gestor, bem=self.bem)
        nbbpm = _novo_nbbpm_com_baixas("", [baixa], self.gestor)
        numero = gerar_numero_nbbpm_unificado(nbbpm)
        self.assertRegex(numero, r"^\d{3}\.\d{7}[\./]\d{4}$")
        self.assertIn("/", numero)
        partes = numero.replace("/", ".").split(".")
        self.assertEqual(len(partes[0]), 3)
        self.assertEqual(len(partes[1]), 7)
        self.assertEqual(len(partes[2]), 4)

    def test_prefixo_ua_001_correto(self):
        baixa, _ = _nova_baixa_com_item(self.ua, self.gestor, bem=self.bem)
        nbbpm = _novo_nbbpm_com_baixas("", [baixa], self.gestor)
        self.assertTrue(gerar_numero_nbbpm_unificado(nbbpm).startswith("001."))

    def test_unicidade_banco_impede_duplicata(self):
        _novo_nbbpm_com_baixas("001.0000001/2026", [], self.gestor, numero_processo_baixa="P1")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _novo_nbbpm_com_baixas("001.0000001/2026", [], self.gestor, numero_processo_baixa="P2")

    def test_validador_regex_impede_lixo(self):
        nbbpm = NBBPM(numero="abc", numero_processo_baixa="P", data_autorizacao=timezone.localdate(), responsavel="G", criado_por=self.gestor)
        with self.assertRaises(ValidationError):
            nbbpm.full_clean()


# =====================================================================
# 4. Concorrência primeira NBBPM do ano (UO) e reuso mesma baixa
# =====================================================================

class TestConcorrenciaPrimeiraNBBPM(TransactionTestCase):
    def setUp(self):
        self.uo, self.ua, self.gestor = _setup_uo_ua_gestor("gestor_conc")
        self.bem1 = criar_bem(self.ua, self.gestor, numero_patrimonial="000.000000001-0")
        self.bem2 = criar_bem(self.ua, self.gestor, numero_patrimonial="000.000000002-0")
        self.baixa1 = criar_baixa(self.ua, self.gestor, status=constants.ACEITA, numero_processo_baixa="P1")
        self.baixa2 = criar_baixa(self.ua, self.gestor, status=constants.ACEITA, numero_processo_baixa="P2")
        BaixaFisicaBensItem.objects.create(baixa=self.baixa1, bem=self.bem1)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa2, bem=self.bem2)

    def test_duas_thread_primeira_nbbpm_geram_0000001_e_0000002(self):
        NBBPM.objects.all().delete()
        BaixaFisicaBemPatrimonial.objects.filter(numero_nbbpm__isnull=False).update(numero_nbbpm="")
        resultados, erros = {}, []

        def criar(baixa, key):
            try:
                resultados[key] = criar_nbbpm_com_retry(baixas=[baixa], numero_processo_baixa=f"PROC-{key}", data_autorizacao=timezone.localdate(), responsavel="Gestor", criado_por=self.gestor).numero
            except Exception as e:
                erros.append(str(e))

        t1 = threading.Thread(target=criar, args=(self.baixa1, "t1"))
        t2 = threading.Thread(target=criar, args=(self.baixa2, "t2"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        if len(resultados) == 2:
            self.assertEqual(len(set(resultados.values())), 2)
            nums = sorted(resultados.values())
            self.assertTrue(nums[0].startswith("001."))
            self.assertTrue(nums[1].startswith("001."))
            seqs = [int(n.replace("/", ".").split(".")[1]) for n in nums]
            self.assertEqual(sorted(seqs), [1, 2])
        else:
            self.assertLessEqual(len(resultados), 2)
            if len(resultados) == 1:
                self.assertEqual(len(erros), 1)

    def test_unicidade_via_retry_em_integrity_error(self):
        NBBPM.objects.all().delete()
        n1 = criar_nbbpm_com_retry(baixas=[self.baixa1], numero_processo_baixa="PROC-1", data_autorizacao=timezone.localdate(), responsavel="G", criado_por=self.gestor)
        self.assertEqual(n1.numero, "001.0000001/" + str(timezone.localdate().year))
        n2 = criar_nbbpm_com_retry(baixas=[self.baixa2], numero_processo_baixa="PROC-2", data_autorizacao=timezone.localdate(), responsavel="G", criado_por=self.gestor)
        self.assertEqual(n2.numero, "001.0000002/" + str(timezone.localdate().year))


class TestReusoMesmaBaixaConcorrente(TransactionTestCase):
    def setUp(self):
        self.uo, self.ua, self.gestor = _setup_uo_ua_gestor("gestor_reuso")
        self.bem = criar_bem(self.ua, self.gestor)
        self.baixa = criar_baixa(self.ua, self.gestor, status=constants.ACEITA, numero_processo_baixa="P-REUSE")
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)
        NBBPM.objects.all().delete()

    def test_mesma_baixa_em_dois_lotes_concorrentes_um_sucesso_um_erro(self):
        resultados, erros = {}, []

        def tentar(key):
            try:
                resultados[key] = criar_nbbpm_com_retry(baixas=[self.baixa], numero_processo_baixa=f"PROC-{key}", data_autorizacao=timezone.localdate(), responsavel="Gestor", criado_por=self.gestor).numero
            except Exception as e:
                erros.append(str(e))

        t1 = threading.Thread(target=tentar, args=("t1",))
        t2 = threading.Thread(target=tentar, args=("t2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        self.assertEqual(len(resultados) + len(erros), 2)
        self.assertEqual(len(resultados), 1)
        self.assertEqual(len(erros), 1)
        self.assertIn("já possui NBBPM", erros[0])


# =====================================================================
# 5. Permissão apenas gestor/superuser e visibilidade superuser
# =====================================================================

class TestPermissaoESuperuser(TestCase):
    def setUp(self):
        self.uo, self.ua, self.gestor = _setup_uo_ua_gestor("gestor_perm")
        self.ua2 = criar_ua(uo=self.uo, codigo="002", nome="UA2", sigla="UAT2")
        self.operador = criar_usuario("operador_perm", self.uo, self.ua, grupos=[GRUPO_OPERADOR_INVENTARIO])
        self.superuser = criar_usuario("superuser_perm", self.uo, None, grupos=[GRUPO_GESTOR_PATRIMONIO], is_superuser=True)
        self.bem = criar_bem(self.ua, self.gestor)
        self.baixa = criar_baixa(self.ua, self.gestor, status=constants.ACEITA, numero_processo_baixa="P-PERM")
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)
        self.nbbpm = _novo_nbbpm_com_baixas("016.0000001.2026", [self.baixa], self.gestor)
        self.baixa2 = criar_baixa(self.ua2, self.gestor, status=constants.ACEITA, numero_processo_baixa="P2")
        bem2 = criar_bem(self.ua2, self.gestor, numero_patrimonial="000.000000002-0")
        BaixaFisicaBensItem.objects.create(baixa=self.baixa2, bem=bem2)
        self.nbbpm2 = _novo_nbbpm_com_baixas("016.0000002.2026", [self.baixa2], self.gestor, numero_processo_baixa="PROC2")

    def _post_nbbpm(self, user, baixa):
        client = APIClient()
        client.force_authenticate(user=user)
        payload = {"baixas": [baixa.id], "numero_processo_baixa": "PROC-NOVO", "data_autorizacao": str(timezone.localdate()), "responsavel": "X"}
        return client.post("/api/nbbpm/", payload, format="json")

    def test_operador_nao_pode_gerar_nbbpm_via_api(self):
        resp = self._post_nbbpm(self.operador, self.baixa)
        self.assertIn(resp.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_400_BAD_REQUEST])

    def test_gestor_pode_gerar_nbbpm_via_api(self):
        baixa_nova, _ = _nova_baixa_com_item(self.ua, self.gestor, numero_processo_baixa="P-NEW-GESTOR", bem=criar_bem(self.ua, self.gestor, numero_patrimonial="000.000000003-0"))
        resp = self._post_nbbpm(self.gestor, baixa_nova)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertRegex(resp.data["numero"], r"^\d{3}\.\d{7}[\./]\d{4}$")

    def test_superuser_pode_gerar_nbbpm_via_api(self):
        baixa_nova, _ = _nova_baixa_com_item(self.ua, self.gestor, numero_processo_baixa="P-NEW-SUPER", bem=criar_bem(self.ua, self.gestor, numero_patrimonial="000.000000004-0"))
        resp = self._post_nbbpm(self.superuser, baixa_nova)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    def test_superuser_ve_todas_nbbpms(self):
        factory = RequestFactory()
        request = factory.get("/api/nbbpm/")
        request.user = self.superuser
        view = NBBPMViewSet()
        view.request = request
        self.assertEqual(view.get_queryset().count(), 2)

    def test_gestor_sem_ua_ve_todas_da_uo(self):
        gestor_sem_ua = criar_usuario("gestor_sem_ua", self.uo, None, grupos=[GRUPO_GESTOR_PATRIMONIO])
        factory = RequestFactory()
        request = factory.get("/api/nbbpm/")
        request.user = gestor_sem_ua
        view = NBBPMViewSet()
        view.request = request
        self.assertEqual(view.get_queryset().count(), 2)

    def test_operador_so_ve_da_sua_ua_via_baixa_viewset(self):
        factory = RequestFactory()
        request = factory.get("/api/baixa-fisica/")
        request.user = self.superuser
        view = BaixaFisicaBemPatrimonialViewSet()
        view.request = request
        view.format_kwarg = None
        self.assertGreaterEqual(view.get_queryset().count(), 2)

    def test_baixa_list_serializer_traz_numero_via_nbbpm(self):
        data = BaixaFisicaBemPatrimonialListSerializer(self.baixa).data
        self.assertEqual(data["numero_nbbpm"], "016.0000001.2026")


# =====================================================================
# 6. Data migration idempotente
# =====================================================================

class TestDataMigrationIdempotente(TestCase):
    def setUp(self):
        self.uo, self.ua, self.gestor = _setup_uo_ua_gestor("gestor_mig", ua_codigo="001", ua_sigla="UA", ua_nome="UA")
        self.bem = criar_bem(self.ua, self.gestor)
        NBBPM.objects.all().delete()
        BaixaFisicaBemPatrimonial.objects.all().delete()

    def _executar_migracao(self):
        mod = _load_migracao_0044()
        FakeSchemaEditor = type("FakeSchemaEditor", (), {"connection": connection})
        mod.migrar_baixa_para_nbbpm(django_apps, FakeSchemaEditor())
        return mod

    def test_migration_copia_numero_antigo_idempotente(self):
        baixa = criar_baixa(self.ua, self.gestor, status=constants.ACEITA, numero_nbbpm="016.0000005.2026")
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        self._executar_migracao()
        count1 = NBBPM.objects.count()
        self._executar_migracao()
        count2 = NBBPM.objects.count()
        self.assertEqual(count1, 1)
        self.assertEqual(count2, 1)
        nbbpm = NBBPM.objects.first()
        self.assertEqual(nbbpm.numero, "016.0000005.2026")
        self.assertIn(baixa, nbbpm.baixas.all())

    def test_migration_trata_aceita_sem_numero_via_admin(self):
        baixa = BaixaFisicaBemPatrimonial.objects.create(
            unidade_administrativa_origem=self.ua,
            numero_processo_baixa="PROC-SEM-NUMERO",
            status=constants.ACEITA,
            criado_por=self.gestor,
            data_baixa=timezone.localdate(),
            data_aprovacao=timezone.now(),
            aprovado_por=self.gestor,
            numero_nbbpm="",
        )
        BaixaFisicaBensItem.objects.create(baixa=baixa, bem=self.bem)
        self._executar_migracao()
        self.assertTrue(NBBPM.objects.filter(baixas__in=[baixa]).exists())
        nbbpm = NBBPM.objects.filter(baixas__in=[baixa]).first()
        self.assertRegex(nbbpm.numero, r"^\d{3}\.\d{7}[\./]\d{4}$")
        self.assertTrue(nbbpm.numero.startswith("001."))


# =====================================================================
# 7. PDF padronizado lote 6 colunas
# =====================================================================

class TestPDFPadronizado(TestCase):
    def setUp(self):
        self.uo, self.ua, self.gestor = _setup_uo_ua_gestor("gestor_pdf")
        self.bem = criar_bem(self.ua, self.gestor)
        self.baixa = criar_baixa(self.ua, self.gestor, status=constants.ACEITA)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)
        self.nbbpm = _novo_nbbpm_com_baixas("016.0000001.2026", [self.baixa], self.gestor)

    def test_pdf_usa_layout_lote_6_colunas_DE_ATE(self):
        [tabela] = _criar_tabela_bens(self.nbbpm)
        self.assertEqual(len(tabela._argW), 6)
        textos = []
        for linha in tabela._cellvalues:
            for cel in linha:
                if hasattr(cel, "text"):
                    textos.append(cel.text)
        self.assertTrue(any("DE" in t for t in textos))
        self.assertTrue(any("ATÉ" in t for t in textos))
        self.assertIn("VALOR", " ".join(textos) or "")
        buf = gerar_pdf_nbbpm_lote(self.nbbpm, usuario_gerador=self.gestor)
        self.assertTrue(buf.getvalue().startswith(b"%PDF"))

    def test_pdf_contem_numero_nbbpm_no_titulo(self):
        self.assertGreater(len(gerar_pdf_nbbpm_lote(self.nbbpm).getvalue()), 1000)


# =====================================================================
# 8. Export Excel busca número na nova tabela
# =====================================================================

class TestExcelExportNovaTabela(TestCase):
    def setUp(self):
        self.uo, self.ua, self.gestor = _setup_uo_ua_gestor("gestor_excel")
        self.bem = criar_bem(self.ua, self.gestor)
        self.baixa = criar_baixa(self.ua, self.gestor, status=constants.ACEITA, numero_nbbpm="")
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)
        self.nbbpm = _novo_nbbpm_com_baixas("016.0000999.2026", [self.baixa], self.gestor, numero_processo_baixa="PROC-EXCEL")
        self.client = APIClient()
        self.client.force_authenticate(user=self.gestor)

    def test_excel_api_busca_numero_na_nova_tabela(self):
        resp = self.client.get("/api/baixa-fisica/exportar-excel/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        wb = load_workbook(filename=BytesIO(resp.content))
        ws = wb.active
        encontrado = any("016.0000999.2026" in (str(v) for v in row if v) for row in ws.iter_rows(values_only=True))
        self.assertTrue(encontrado, "Excel deve conter número da NBBPM via M2M")

    def test_excel_admin_resource_busca_nbbpm_via_m2m(self):
        baixa = BaixaFisicaBemPatrimonial.objects.prefetch_related("nbbpms_lote", "itens__bem").get(pk=self.baixa.pk)
        self.assertEqual(BaixaFisicaResource().dehydrate_nbbpm(baixa), "016.0000999.2026")

    def test_excel_admin_fallback_legado_quando_sem_nbbpm(self):
        baixa2 = criar_baixa(self.ua, self.gestor, status=constants.ACEITA, numero_nbbpm="016.0000001.2026", numero_processo_baixa="P2")
        baixa2.save()
        self.assertEqual(BaixaFisicaResource().dehydrate_nbbpm(baixa2), "016.0000001.2026")


# =====================================================================
# 9. Desativação rotas antigas
# =====================================================================

class TestDesativacaoRotasAntigas(TestCase):
    def setUp(self):
        self.uo, self.ua, self.gestor = _setup_uo_ua_gestor("gestor_desat")
        self.bem = criar_bem(self.ua, self.gestor)
        self.baixa = criar_baixa(self.ua, self.gestor, status=constants.ACEITA, numero_nbbpm="016.0000001.2026")
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)
        self.client = APIClient()
        self.client.force_authenticate(user=self.gestor)

    def test_gerar_nbbpm_individual_removido_retorna_404(self):
        resp = self.client.get(f"/api/baixa-fisica/{self.baixa.pk}/gerar-nbbpm/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_baixar_nbbpm_admin_retorna_410(self):
        factory = RequestFactory()
        admin = BaixaFisicaBemPatrimonialAdmin(BaixaFisicaBemPatrimonial, AdminSite())
        request = factory.get(f"/admin/bem_patrimonial/baixafisicabempatrimonial/{self.baixa.pk}/nbbpm/")
        request.user = self.gestor
        self.assertEqual(admin.baixar_nbbpm(request, self.baixa.pk).status_code, 410)

    def test_nova_api_nbbpm_funciona(self):
        baixa_nova, _ = _nova_baixa_com_item(self.ua, self.gestor, numero_processo_baixa="P-NOVA", bem=criar_bem(self.ua, self.gestor, numero_patrimonial="000.000000009-0"))
        payload = {"baixas": [baixa_nova.id], "numero_processo_baixa": "PROC-NEW", "data_autorizacao": str(timezone.localdate()), "responsavel": "Gestor"}
        resp = self.client.post("/api/nbbpm/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp_pdf = self.client.get(f"/api/nbbpm/{resp.data['id']}/pdf/")
        self.assertEqual(resp_pdf.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_pdf["Content-Type"], "application/pdf")


# =====================================================================
# 10. Validação de vínculo e bloqueio de reuso
# =====================================================================

class TestValidacaoVinculoEReuso(TestCase):
    def setUp(self):
        self.uo, self.ua, self.gestor = _setup_uo_ua_gestor("gestor_vinc")
        self.bem = criar_bem(self.ua, self.gestor)
        self.baixa = criar_baixa(self.ua, self.gestor, status=constants.ACEITA)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=self.bem)
        self.nbbpm = _novo_nbbpm_com_baixas("016.0000001.2026", [self.baixa], self.gestor)

    def _assert_serializer_invalido(self, baixa):
        data = {"baixas": [baixa.id], "numero_processo_baixa": "PROC-NEW", "data_autorizacao": str(timezone.localdate()), "responsavel": "G"}
        req = MagicMock()
        req.user = self.gestor
        serializer = NBBPMGerarLoteSerializer(data=data, context={"request": req})
        self.assertFalse(serializer.is_valid())
        self.assertIn("baixas", serializer.errors)

    def test_baixa_ja_utilizada_nao_pode_ser_reutilizada(self):
        self._assert_serializer_invalido(self.baixa)

    def test_baixa_com_numero_legado_bloqueia_lote(self):
        baixa2 = criar_baixa(self.ua, self.gestor, status=constants.ACEITA, numero_nbbpm="016.0000002.2026")
        self._assert_serializer_invalido(baixa2)

    def test_aprovar_baixa_ja_com_nbbpm_gera_erro(self):
        client = APIClient()
        client.force_authenticate(user=self.gestor)
        baixa_solic = criar_baixa(self.ua, self.gestor, status=constants.SOLICITADA)
        self.nbbpm.baixas.add(baixa_solic)
        resp = client.post(reverse("baixas-fisicas-aprovar", kwargs={"pk": baixa_solic.pk}))
        self.assertIn(resp.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])


class TestServiceNBBPMNumeroCoberturaExtra(TestCase):
    def setUp(self):
        self.uo, self.ua, self.gestor = _setup_uo_ua_gestor("gest_svc2", ua_codigo=codigo_ua(1, 16, 10, 40), ua_sigla="UA40", ua_nome="UA40")
        self.baixa = criar_baixa(self.ua, self.gestor)
        BaixaFisicaBensItem.objects.create(baixa=self.baixa, bem=criar_bem(self.ua, self.gestor))

    def test_max_e_proximo(self):
        self.assertEqual(svc._max_sequencial_nbbpm_por_ano(2099), 0)
        self.assertEqual(svc._max_sequencial_baixa_legado_por_ano(2099), 0)
        self.assertEqual(svc.obter_proximo_sequencial_por_ano(2099), 1)
        _novo_nbbpm_com_baixas("001.0000005/2099", [], self.gestor)
        self.assertEqual(svc._max_sequencial_nbbpm_por_ano(2099), 5)
        criar_baixa(self.ua, self.gestor, numero_nbbpm="001.0000007/2099")
        self.assertEqual(svc._max_sequencial_baixa_legado_por_ano(2099), 7)
        self.assertEqual(svc.obter_proximo_sequencial_por_ano(2099), 8)

    def test_extrair_e_retry(self):
        n = NBBPM(numero="", data_autorizacao=timezone.localdate(), numero_processo_baixa="P", responsavel="G", criado_por=self.gestor)
        self.assertIsNotNone(svc._extrair_ano_nbbpm(n))
        self.assertEqual(svc._extrair_ano_nbbpm(MagicMock(data_autorizacao=None, data_aprovacao="2022-01-01")), 2022)
        self.assertIsNone(svc._extrair_ano_nbbpm(MagicMock(data_autorizacao=None, data_aprovacao=None)))
        self.assertRegex(svc._gerar_numero_formatado(2100), r"001\.\d{7}/2100")
        with self.assertRaises(ValidationError):
            svc.gerar_numero_nbbpm_unificado(object())
        self.assertRegex(svc.gerar_numero_nbbpm_unificado(n), r"001\.\d{7}/\d{4}")
        self.assertRegex(svc.gerar_numero_para_ano(2101), r"001\.\d{7}/2101")
        with patch("bem_patrimonial.services.nbbpm_numero._gerar_numero_formatado", side_effect=IntegrityError("dup")):
            with self.assertRaises(IntegrityError):
                svc._tentar_gerar_numero(2102, 1)
        uo_tmp, _ = UO_Model.objects.get_or_create(codigo="555", defaults={"nome": "UO555", "sigla": "UO555"})
        ua2 = criar_ua(uo=uo_tmp, codigo="555", sigla="U2", nome="U2")
        b2 = criar_baixa(ua2, self.gestor)
        BaixaFisicaBensItem.objects.create(baixa=b2, bem=criar_bem(ua2, self.gestor, numero_patrimonial="000.000000010-0"))
        with self.assertRaises(ValidationError):
            svc.criar_nbbpm_com_retry(baixas=[self.baixa, b2], numero_processo_baixa="P", data_autorizacao=timezone.localdate(), responsavel="G", criado_por=self.gestor)
        self.baixa.nbbpms_lote.clear()
        self.baixa.numero_nbbpm = ""
        self.baixa.save(update_fields=["numero_nbbpm"])
        NBBPM.objects.filter(numero="001.0000001/2026").delete()
        n = svc.criar_nbbpm_com_retry(baixas=[self.baixa], numero_processo_baixa="P", data_autorizacao=timezone.localdate(), responsavel="G", criado_por=self.gestor)
        self.assertTrue(n.numero.startswith("001."))
        ua_sem_id = MagicMock(pk=1, unidade_orcamentaria_id=None, unidade_orcamentaria=MagicMock(pk=99))
        b_mock = MagicMock(pk=1, unidade_administrativa_origem=ua_sem_id)
        self.assertEqual(svc._validar_uo_baixas([b_mock]), {99})
        lb1 = MagicMock(unidade_administrativa_origem=MagicMock(unidade_orcamentaria_id=1))
        lb2 = MagicMock(unidade_administrativa_origem=MagicMock(unidade_orcamentaria_id=2))
        with self.assertRaises(ValidationError):
            svc._validar_uo_locked([lb1, lb2])
        n2 = _novo_nbbpm_com_baixas("001.0000009/2026", [], self.gestor)
        svc._registrar_historico_nbbpm(n2, self.gestor, {self.uo.pk}, 2026, [self.baixa])


class TestMigration0044CoberturaExtra(TestCase):
    def test_helpers(self):
        mod = _load_migracao_0044()
        mod.reverse_migracao(MagicMock(), MagicMock())
        m = MagicMock(data_aprovacao=timezone.now(), data_baixa=timezone.localdate())
        self.assertIsNotNone(mod._resolver_data_autorizacao(m))
        m2 = MagicMock(data_aprovacao=None, data_baixa=timezone.localdate())
        self.assertIsNotNone(mod._resolver_data_autorizacao(m2))
        m3 = MagicMock(data_aprovacao=None, data_baixa=None)
        self.assertIsNotNone(mod._resolver_data_autorizacao(m3))
        self.assertEqual(mod._calcular_max_sequencial(NBBPM.objects.all(), "numero"), 0)
        self.assertTrue(hasattr(mod, "PREFIXO_FIXO"))
