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

from bem_patrimonial import constants as bem_constants
from bem_patrimonial.models import BemPatrimonial
from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua, codigo_uo
from dados_comuns.tests.factories import criar_ua, criar_uo
from inventario import constants as inv_constants
from inventario.models import ConciliacaoUA
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
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


class ImportacaoBensPorPerfilTestCase(APITransactionTestCase):
    """
    Fluxo de aprovação da importação conforme o perfil do usuário autenticado.

    Regra de negócio (história):
    - Gestor de Patrimônio: bens importados são incorporados imediatamente à
      listagem da Unidade Administrativa (status APROVADO), dispensando a
      etapa de aprovação.
    - Operador de Inventário: mantém o fluxo atual, entrando com status
      Aguardando Aprovação até que um Gestor aprove.

    A alteração impacta exclusivamente o fluxo de importação; nenhuma
    Conciliação em aberto existe nestes cenários para isolar a regra de perfil.
    """

    def setUp(self):
        super().setUp()

        self.uo = criar_uo(codigo=codigo_uo(30, 30, 30), nome="UO Perfil", sigla="UOP")
        self.ua = criar_ua(
            uo=self.uo,
            codigo=codigo_ua(30, 30, 30, 1),
            sigla="UAP",
            nome="Unidade Perfil",
        )

        self.grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        self.grupo_operador = Group.objects.get_or_create(
            name=GRUPO_OPERADOR_INVENTARIO
        )[0]

        self.gestor = Usuario.objects.create_user(
            username="gestor_perfil",
            email="gestor.perfil@test.com",
            **auth_kwargs("test123"),
            nome="Gestor Perfil",
            is_staff=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.gestor.groups.add(self.grupo_gestor)

        self.operador = Usuario.objects.create_user(
            username="operador_perfil",
            email="operador.perfil@test.com",
            **auth_kwargs("test123"),
            nome="Operador Perfil",
            is_staff=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.operador.groups.add(self.grupo_operador)
        self.operador.unidades_administrativas.add(self.ua)

        self.client = APIClient()

    # ------------------------------------------------------------------
    # Gestor de Patrimônio: incorporação imediata (APROVADO)
    # ------------------------------------------------------------------

    def test_gestor_importa_bem_entra_aprovado(self):
        self.client.force_authenticate(self.gestor)
        arquivo = _planilha_valida(
            [["001.000000101-0", "Notebook", "Notebook Dell", "1500,00", "Dell", "Latitude"]]
        )

        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            msg=f"Resposta inesperada: {response.status_code} — {response.data}",
        )
        bem = BemPatrimonial.objects.get(numero_patrimonial="001.000000101-0")
        self.assertEqual(bem.status, bem_constants.APROVADO)

    def test_gestor_importa_response_sinaliza_aprovacao_automatica(self):
        self.client.force_authenticate(self.gestor)
        arquivo = _planilha_valida(
            [["001.000000102-0", "Monitor", "Monitor 24pol", "800,00", "LG", "24ML"]]
        )

        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )

        self.assertTrue(response.data.get("aprovacao_automatica"))

    def test_gestor_importa_registra_historico_aprovado(self):
        self.client.force_authenticate(self.gestor)
        arquivo = _planilha_valida(
            [["001.000000103-0", "Cadeira", "Cadeira ergonômica", "300,00", "Flexform", "Cavaletti"]]
        )

        self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )

        bem = BemPatrimonial.objects.get(numero_patrimonial="001.000000103-0")
        self.assertTrue(
            bem.statusbempatrimonial_set.filter(
                status=bem_constants.APROVADO
            ).exists()
        )

    # ------------------------------------------------------------------
    # Operador de Inventário: mantém fluxo de aprovação
    # ------------------------------------------------------------------

    def test_operador_importa_bem_fica_aguardando_aprovacao(self):
        self.client.force_authenticate(self.operador)
        arquivo = _planilha_valida(
            [["001.000000201-0", "Impressora", "Impressora laser", "600,00", "HP", "LaserJet"]]
        )

        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            msg=f"Resposta inesperada: {response.status_code} — {response.data}",
        )
        bem = BemPatrimonial.objects.get(numero_patrimonial="001.000000201-0")
        self.assertEqual(bem.status, bem_constants.AGUARDANDO_APROVACAO)

    def test_operador_importa_response_nao_sinaliza_aprovacao_automatica(self):
        self.client.force_authenticate(self.operador)
        arquivo = _planilha_valida(
            [["001.000000202-0", "Teclado", "Teclado sem fio", "150,00", "Logitech", "K380"]]
        )

        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )

        self.assertFalse(response.data.get("aprovacao_automatica"))

    def test_operador_importa_nao_registra_historico_aprovado(self):
        self.client.force_authenticate(self.operador)
        arquivo = _planilha_valida(
            [["001.000000203-0", "Mouse", "Mouse sem fio", "80,00", "Logitech", "M170"]]
        )

        self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )

        bem = BemPatrimonial.objects.get(numero_patrimonial="001.000000203-0")
        self.assertFalse(
            bem.statusbempatrimonial_set.filter(
                status=bem_constants.APROVADO
            ).exists()
        )

    # ------------------------------------------------------------------
    # Regressão: importação por usuário sem UA não pode dar "falso sucesso"
    # ------------------------------------------------------------------

    def test_usuario_sem_ua_nao_retorna_falso_sucesso(self):
        """
        Regressão: antes, um usuário sem Unidade Administrativa vinculada
        recebia 201 ("bem disponível na listagem"), mas nenhum bem era salvo
        (a ValidationError de before_import era engolida por raise_errors=
        False e ficava só em result.base_errors). O bem então "sumia" da
        listagem. Agora a resposta deve ser 403 e nenhum bem pode ser criado.
        """
        gestor_sem_ua = Usuario.objects.create_user(
            username="gestor_sem_ua_perfil",
            email="gestor.sem.ua.perfil@test.com",
            **auth_kwargs("test123"),
            nome="Gestor Sem UA Perfil",
            is_staff=True,
            unidade_orcamentaria=self.uo,
        )
        gestor_sem_ua.groups.add(self.grupo_gestor)
        self.client.force_authenticate(gestor_sem_ua)

        arquivo = _planilha_valida(
            [["001.000000301-0", "Notebook", "Notebook Dell", "1500,00", "Dell", "Latitude"]]
        )
        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            BemPatrimonial.objects.filter(
                numero_patrimonial="001.000000301-0"
            ).exists(),
            "Nenhum bem deve ser criado quando o usuário não tem UA vinculada.",
        )


class ImportacaoUnidadeAdministrativaDestinoTestCase(APITransactionTestCase):
    """
    Escolha da Unidade Administrativa de destino na importação.

    Regra:
    - Usuário logado numa UA: os bens vão para a UA do usuário (sem precisar
      enviar unidade_administrativa_id).
    - Usuário logado numa UO (sem UA direta): o front envia
      unidade_administrativa_id com a UA escolhida; o backend valida que ela
      pertence ao escopo do usuário e grava os bens nessa UA.
    """

    def setUp(self):
        super().setUp()

        self.uo = criar_uo(codigo=codigo_uo(40, 40, 40), nome="UO Dest", sigla="UOD")
        self.ua1 = criar_ua(
            uo=self.uo, codigo=codigo_ua(40, 40, 40, 1), sigla="UAD1", nome="UA Dest 1"
        )
        self.ua2 = criar_ua(
            uo=self.uo, codigo=codigo_ua(40, 40, 40, 2), sigla="UAD2", nome="UA Dest 2"
        )
        self.grupo_gestor = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]

        # Gestor logado na UO (sem UA direta).
        self.gestor_uo = Usuario.objects.create_user(
            username="gestor_uo_dest",
            email="gestor.uo.dest@test.com",
            **auth_kwargs("test123"),
            nome="Gestor UO Dest",
            is_staff=True,
            unidade_orcamentaria=self.uo,
        )
        self.gestor_uo.groups.add(self.grupo_gestor)

        # Gestor logado numa UA direta.
        self.gestor_ua = Usuario.objects.create_user(
            username="gestor_ua_dest",
            email="gestor.ua.dest@test.com",
            **auth_kwargs("test123"),
            nome="Gestor UA Dest",
            is_staff=True,
            unidade_administrativa=self.ua1,
            unidade_orcamentaria=self.uo,
        )
        self.gestor_ua.groups.add(self.grupo_gestor)

        self.client = APIClient()

    def test_uo_com_ua_escolhida_grava_na_ua(self):
        self.client.force_authenticate(self.gestor_uo)
        arquivo = _planilha_valida(
            [["001.000000401-0", "Note", "Desc", "10,00", "M", "X"]]
        )
        response = self.client.post(
            "/api/bens/importar/",
            {"arquivo": arquivo, "unidade_administrativa_id": self.ua2.id},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        bem = BemPatrimonial.objects.get(numero_patrimonial="001.000000401-0")
        self.assertEqual(bem.unidade_administrativa_id, self.ua2.id)

    def test_uo_sem_ua_escolhida_retorna_403(self):
        self.client.force_authenticate(self.gestor_uo)
        arquivo = _planilha_valida(
            [["001.000000402-0", "Note", "Desc", "10,00", "M", "X"]]
        )
        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            BemPatrimonial.objects.filter(
                numero_patrimonial="001.000000402-0"
            ).exists()
        )

    def test_uo_com_ua_fora_do_escopo_retorna_403(self):
        outra_uo = criar_uo(codigo=codigo_uo(50, 50, 50), nome="UO X", sigla="UOX")
        ua_fora = criar_ua(
            uo=outra_uo, codigo=codigo_ua(50, 50, 50, 1), sigla="UAX", nome="UA Fora"
        )
        self.client.force_authenticate(self.gestor_uo)
        arquivo = _planilha_valida(
            [["001.000000403-0", "Note", "Desc", "10,00", "M", "X"]]
        )
        response = self.client.post(
            "/api/bens/importar/",
            {"arquivo": arquivo, "unidade_administrativa_id": ua_fora.id},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            BemPatrimonial.objects.filter(
                numero_patrimonial="001.000000403-0"
            ).exists()
        )

    def test_ua_direta_ignora_ua_id_e_usa_a_do_usuario(self):
        # Usuário com UA direta: mesmo que um id seja enviado, a UA do usuário
        # prevalece por já estar no escopo (filtrar_ua_origem_por_escopo só
        # devolve a própria UA quando o usuário tem UA direta).
        self.client.force_authenticate(self.gestor_ua)
        arquivo = _planilha_valida(
            [["001.000000404-0", "Note", "Desc", "10,00", "M", "X"]]
        )
        response = self.client.post(
            "/api/bens/importar/",
            {"arquivo": arquivo, "unidade_administrativa_id": self.ua2.id},
            format="multipart",
        )
        # ua2 não está no escopo de quem tem ua1 como UA direta -> 403.
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_ua_direta_sem_ua_id_grava_na_ua_do_usuario(self):
        self.client.force_authenticate(self.gestor_ua)
        arquivo = _planilha_valida(
            [["001.000000405-0", "Note", "Desc", "10,00", "M", "X"]]
        )
        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        bem = BemPatrimonial.objects.get(numero_patrimonial="001.000000405-0")
        self.assertEqual(bem.unidade_administrativa_id, self.ua1.id)


class ImportacaoDescartaLinhasVaziasTestCase(APITransactionTestCase):
    """
    Linhas 100% vazias na planilha são descartadas silenciosamente; apenas as
    linhas preenchidas são importadas. Linha parcialmente preenchida continua
    sendo erro (campo obrigatório em branco), rejeitando a carga (tudo ou nada).
    """

    def setUp(self):
        super().setUp()
        self.uo = criar_uo(codigo=codigo_uo(60, 60, 60), nome="UO Vazias", sigla="UOV")
        self.ua = criar_ua(
            uo=self.uo, codigo=codigo_ua(60, 60, 60, 1), sigla="UAV", nome="UA Vazias"
        )
        self.gestor = Usuario.objects.create_user(
            username="gestor_vazias",
            email="gestor.vazias@test.com",
            **auth_kwargs("test123"),
            nome="Gestor Vazias",
            is_staff=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.gestor.groups.add(
            Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        )
        self.client = APIClient()
        self.client.force_authenticate(self.gestor)

    def test_descarta_linhas_vazias_e_importa_preenchidas(self):
        arquivo = _planilha_valida(
            [
                ["001.000000601-0", "Note", "Desc", "10,00", "M", "X"],
                ["", "", "", "", "", ""],                      # 100% vazia
                [None, None, None, None, None, None],          # 100% vazia
                ["   ", "  ", "", "  ", "", ""],               # só espaços
                ["001.000000602-0", "Mouse", "Desc", "5,00", "M", "Y"],
            ]
        )
        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["importados"], 2)
        self.assertEqual(
            BemPatrimonial.objects.filter(
                numero_patrimonial__in=["001.000000601-0", "001.000000602-0"]
            ).count(),
            2,
        )

    def test_linha_parcialmente_preenchida_continua_erro(self):
        arquivo = _planilha_valida(
            [
                ["001.000000603-0", "Note", "Desc", "10,00", "M", "X"],
                ["", "Mouse", "", "", "", ""],                 # parcial -> erro
            ]
        )
        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )
        self.assertEqual(
            response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY, response.data
        )
        self.assertFalse(
            BemPatrimonial.objects.filter(
                numero_patrimonial="001.000000603-0"
            ).exists()
        )

    def test_planilha_apenas_com_linhas_vazias_e_tratada_como_vazia(self):
        arquivo = _planilha_valida(
            [
                ["", "", "", "", "", ""],
                [None, None, None, None, None, None],
            ]
        )
        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )
        self.assertEqual(
            response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY, response.data
        )
        self.assertIn("vazia", str(response.data).lower())


class ImportacaoUAEscopoPorPerfilTestCase(APITransactionTestCase):
    """
    Regressão do incidente: a UA escolhida no seletor (frontend) deve ser
    aceita pelo backend para TODOS os perfis que a enxergam no seletor —
    inclusive Operador de Inventário e superusuário logados numa UO. Antes, a
    validação usava a regra de movimentação (que ignora esses perfis) e recusava
    a importação com a mensagem de "UA não vinculada".
    """

    def setUp(self):
        super().setUp()
        self.uo = criar_uo(codigo=codigo_uo(70, 70, 70), nome="UO Esc", sigla="UOE")
        self.ua = criar_ua(
            uo=self.uo, codigo=codigo_ua(70, 70, 70, 1), sigla="UAE", nome="UA Esc"
        )
        self.client = APIClient()

    def _importa(self, user, num):
        self.client.force_authenticate(user)
        return self.client.post(
            "/api/bens/importar/",
            {
                "arquivo": _planilha_valida(
                    [[num, "Note", "Desc", "10,00", "M", "X"]]
                ),
                "unidade_administrativa_id": self.ua.id,
            },
            format="multipart",
        )

    def test_operador_em_uo_com_ua_vinculada_importa(self):
        operador = Usuario.objects.create_user(
            username="op_uo_esc",
            email="op.uo.esc@test.com",
            **auth_kwargs("test123"),
            nome="Op UO Esc",
            is_staff=True,
            unidade_orcamentaria=self.uo,
        )
        operador.groups.add(
            Group.objects.get_or_create(name=GRUPO_OPERADOR_INVENTARIO)[0]
        )
        operador.unidades_administrativas.add(self.ua)

        response = self._importa(operador, "001.000000701-0")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        bem = BemPatrimonial.objects.get(numero_patrimonial="001.000000701-0")
        self.assertEqual(bem.unidade_administrativa_id, self.ua.id)
        # Operador mantém o fluxo de aprovação.
        self.assertEqual(bem.status, bem_constants.AGUARDANDO_APROVACAO)

    def test_superuser_em_uo_importa(self):
        superuser = Usuario.objects.create_user(
            username="su_uo_esc",
            email="su.uo.esc@test.com",
            **auth_kwargs("test123"),
            nome="SU UO Esc",
            is_staff=True,
            is_superuser=True,
            unidade_orcamentaria=self.uo,
        )
        response = self._importa(superuser, "001.000000702-0")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        bem = BemPatrimonial.objects.get(numero_patrimonial="001.000000702-0")
        self.assertEqual(bem.unidade_administrativa_id, self.ua.id)


class ImportacaoNumeroLinhaOriginalTestCase(APITransactionTestCase):
    """
    Os erros devem reportar o número ORIGINAL da linha na planilha, mesmo quando
    há linhas 100% vazias removidas antes da validação. Sem isso, o erro de uma
    linha após uma vazia apareceria com o número deslocado.
    """

    def setUp(self):
        super().setUp()
        self.uo = criar_uo(codigo=codigo_uo(80, 80, 80), nome="UO NL", sigla="UONL")
        self.ua = criar_ua(
            uo=self.uo, codigo=codigo_ua(80, 80, 80, 1), sigla="UANL", nome="UA NL"
        )
        self.gestor = Usuario.objects.create_user(
            username="gestor_nl",
            email="gestor.nl@test.com",
            **auth_kwargs("test123"),
            nome="Gestor NL",
            is_staff=True,
            unidade_administrativa=self.ua,
            unidade_orcamentaria=self.uo,
        )
        self.gestor.groups.add(
            Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)[0]
        )
        self.client = APIClient()
        self.client.force_authenticate(self.gestor)

    def test_erro_reporta_linha_original_apos_vazia(self):
        # 1ª linha de dados: válida | 2ª: vazia (removida) | 3ª: erro (sem descrição)
        arquivo = _planilha_valida(
            [
                ["001.000000811-0", "Note", "Desc", "10,00", "M", "X"],
                ["", "", "", "", "", ""],
                ["001.000000812-0", "Mouse", "", "5,00", "M", "Y"],
            ]
        )
        response = self.client.post(
            "/api/bens/importar/", {"arquivo": arquivo}, format="multipart"
        )
        self.assertEqual(
            response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY, response.data
        )
        linhas_erro = {e["linha"] for e in response.data.get("erros_por_linha", [])}
        # A 3ª linha de dados mantém o número 3 (posição original), não 2.
        self.assertIn(3, linhas_erro)
        self.assertNotIn(2, linhas_erro)
