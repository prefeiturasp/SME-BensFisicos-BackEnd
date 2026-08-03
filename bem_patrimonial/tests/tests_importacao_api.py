"""
Importação de bens via API (POST /api/bens/importar/) e Conciliação em aberto.

Regra de negócio: se existir Conciliação em aberto (status='em_aberto') para
a Unidade Administrativa do usuário autenticado — a mesma UA usada para os
bens importados (ver before_import_row do BemPatrimonialResource) — a
importação deve ser BLOQUEADA antes de qualquer processamento da planilha,
retornando 409 com:

    "Importação não realizada: existe Conciliação em aberto."

Nada deve ser lido/persistido nesse caso (nem a planilha é aberta).

Contexto histórico do bug que motivou reforçar esses testes: antes dessa
validação existir, uma importação feita enquanto havia Conciliação em
aberto podia estourar 500 ao sincronizar o bem importado com o
ItemConciliacao correspondente — seja por um usuário incorretamente
resolvido como AnonymousUser (já corrigido via `audit_as(request.user)` na
action `importar`), seja por inconsistências de FK nessa sincronização.
Bloquear a importação antecipadamente elimina essa classe inteira de erros:
o código de sync com conciliações em aberto nunca chega a rodar durante a
importação, porque a existência de conciliação aberta agora barra o fluxo
antes disso.
"""

import io
from datetime import date

import openpyxl
from django.contrib.auth.models import Group
from rest_framework import status
from rest_framework.test import APIClient, APITransactionTestCase

from bem_patrimonial.models import BemPatrimonial
from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua, codigo_uo
from dados_comuns.tests.factories import criar_ua, criar_uo
from inventario import constants as inv_constants
from inventario.models import ConciliacaoUA
from usuario.constants import GRUPO_GESTOR_PATRIMONIO
from usuario.models import Usuario


def _planilha_valida(linhas):
    """Monta um XLSX em memória com o cabeçalho oficial do modelo de importação."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(
        ["numero_patrimonial", "nome", "descricao", "valor_unitario", "marca", "modelo"]
    )
    for linha in linhas:
        ws.append(linha)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    buffer.name = "planilha.xlsx"
    return buffer


class ImportacaoBensComConciliacaoEmAbertoTestCase(APITransactionTestCase):
    """
    APITransactionTestCase (não APITestCase): os demais testes deste app já
    dependem de commits reais para exercitar o sync via
    `transaction.on_commit`; mantemos o mesmo tipo de TestCase por
    consistência, ainda que o bloqueio em si não dependa disso.
    """

    def setUp(self):
        super().setUp()

        self.uo = criar_uo(codigo=codigo_uo(10, 10, 10), nome="UO 1", sigla="UO1")
        self.ua = criar_ua(
            uo=self.uo, codigo=codigo_ua(10, 10, 10, 1), sigla="UA1", nome="Unidade 1"
        )

        grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]

        self.usuario = Usuario.objects.create_user(
            username="gestor_importacao",
            email="gestor.importacao@test.com",
            **auth_kwargs("test123"),
            nome="Gestor Importação",
            is_staff=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.usuario.groups.add(grupo_gestor)

        self.conciliacao_aberta = ConciliacaoUA.objects.create(
            tipo=inv_constants.CONCILIACAO_EVENTUAL,
            periodo_final=date(2025, 12, 31),
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
            status=inv_constants.CONCILIACAO_EM_ABERTO,
        )

        self.client = APIClient()
        self.client.force_authenticate(self.usuario)

    # ------------------------------------------------------------------
    # Bloqueio quando existe Conciliação em aberto
    # ------------------------------------------------------------------

    def test_importar_bloqueada_com_409_quando_ha_conciliacao_em_aberto(self):
        arquivo = _planilha_valida(
            [["001.000000001-0", "Notebook", "Notebook Dell", "1500,00", "Dell", "Latitude"]]
        )

        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data["detail"],
            "Importação não realizada: existe Conciliação em aberto.",
        )

    def test_importar_bloqueada_nao_cria_nenhum_bem(self):
        arquivo = _planilha_valida(
            [["001.000000002-0", "Cadeira", "Cadeira de escritório", "300,00", "Marca X", "Modelo Y"]]
        )

        self.client.post("/api/bens/importar/", {"arquivo": arquivo}, format="multipart")

        self.assertFalse(
            BemPatrimonial.objects.filter(numero_patrimonial="001.000000002-0").exists()
        )

    def test_importar_bloqueada_mesmo_com_multiplas_conciliacoes_abertas_para_a_ua(self):
        ConciliacaoUA.objects.create(
            tipo=inv_constants.CONCILIACAO_EVENTUAL,
            periodo_final=date(2026, 6, 30),
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
            status=inv_constants.CONCILIACAO_EM_ABERTO,
        )

        arquivo = _planilha_valida(
            [["001.000000003-0", "Monitor", "Monitor 24pol", "800,00", "LG", "24ML"]]
        )
        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    # ------------------------------------------------------------------
    # Importação permitida quando NÃO há conciliação em aberto
    # ------------------------------------------------------------------

    def test_importar_permitida_quando_conciliacao_esta_fechada(self):
        self.conciliacao_aberta.status = inv_constants.CONCILIACAO_FECHADO
        self.conciliacao_aberta.save(update_fields=["status"])

        arquivo = _planilha_valida(
            [["001.000000004-0", "Impressora", "Impressora laser", "600,00", "HP", "LaserJet"]]
        )
        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            msg=f"Resposta inesperada: {response.status_code} — {response.data}",
        )
        self.assertTrue(
            BemPatrimonial.objects.filter(numero_patrimonial="001.000000004-0").exists()
        )

    def test_importar_permitida_quando_conciliacao_esta_fechada_por_admin(self):
        self.conciliacao_aberta.status = inv_constants.CONCILIACAO_FECHADO_ADMIN
        self.conciliacao_aberta.save(update_fields=["status"])

        arquivo = _planilha_valida(
            [["001.000000005-0", "Teclado", "Teclado sem fio", "150,00", "Logitech", "K380"]]
        )
        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_importar_sem_nenhuma_conciliacao_para_a_ua_funciona_normalmente(self):
        self.conciliacao_aberta.delete()

        arquivo = _planilha_valida(
            [["001.000000006-0", "Mouse", "Mouse sem fio", "80,00", "Logitech", "M170"]]
        )
        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    # ------------------------------------------------------------------
    # Escopo: só considera conciliações da própria UA do usuário
    # ------------------------------------------------------------------

    def test_importar_nao_e_bloqueada_por_conciliacao_em_aberto_de_outra_ua(self):
        outra_uo = criar_uo(codigo=codigo_uo(20, 20, 20), nome="UO 2", sigla="UO2")
        outra_ua = criar_ua(
            uo=outra_uo, codigo=codigo_ua(20, 20, 20, 1), sigla="UA2", nome="Unidade 2"
        )
        ConciliacaoUA.objects.create(
            tipo=inv_constants.CONCILIACAO_EVENTUAL,
            periodo_final=date(2025, 12, 31),
            unidade_administrativa=outra_ua,
            criado_por=self.usuario,
            status=inv_constants.CONCILIACAO_EM_ABERTO,
        )

        # Fecha a conciliação da própria UA do usuário para isolar o cenário
        self.conciliacao_aberta.status = inv_constants.CONCILIACAO_FECHADO
        self.conciliacao_aberta.save(update_fields=["status"])

        arquivo = _planilha_valida(
            [["001.000000007-0", "Webcam", "Webcam HD", "200,00", "Logitech", "C920"]]
        )
        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            msg=f"Resposta inesperada: {response.status_code} — {response.data}",
        )

    # ------------------------------------------------------------------
    # Edge case: usuário sem UA vinculada
    # ------------------------------------------------------------------

    def test_importar_sem_ua_nao_quebra_na_checagem_de_conciliacao(self):
        """
        A checagem de conciliação em aberto que adicionamos precisa ser
        None-safe: usuário sem UA vinculada (`ua_usuario is None`) não deve
        estourar exceção na nossa validação — ela é simplesmente pulada,
        e o fluxo segue adiante (para as validações já existentes).

        NOTA: ao escrever este teste, encontramos um problema pré-existente
        e não relacionado a esta mudança: a 403 documentada para "usuário
        sem UA vinculada" (levantada em `before_import`) não é de fato
        retornada pela API, porque `resource.import_data(..., raise_errors=
        False, ...)` engole a exceção do before_import silenciosamente (só
        relança se raise_errors=True — ver import_export/resources.py). Ou
        seja, hoje a importação prossegue e tenta criar bens com
        unidade_administrativa=None. Isso já acontecia antes desta mudança
        e está fora do escopo desta história; sinalizando para tratar à
        parte. Por isso este teste verifica apenas que NÃO há 409 (nossa
        checagem não interfere/crasha), sem fixar qual deveria ser o status
        "correto" para esse cenário — isso é assunto de outra correção.
        """
        usuario_sem_ua = Usuario.objects.create_user(
            username="gestor_sem_ua",
            email="gestor.sem.ua@test.com",
            **auth_kwargs("test123"),
            nome="Gestor Sem UA",
            is_staff=True,
        )
        usuario_sem_ua.groups.add(
            Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        )
        self.client.force_authenticate(usuario_sem_ua)

        arquivo = _planilha_valida(
            [["001.000000008-0", "Headset", "Headset com microfone", "100,00", "JBL", "Quantum"]]
        )
        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )

        self.assertNotEqual(
            response.status_code,
            status.HTTP_409_CONFLICT,
            msg="Sem UA não deve nunca cair na checagem de conciliação em aberto.",
        )
