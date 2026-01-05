import datetime
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Group

from bem_patrimonial.models import BemPatrimonial
from bem_patrimonial import constants as bem_constants
from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario
from usuario.constants import GRUPO_GESTOR_PATRIMONIO

from inventario.models import ConciliacaoUA, ItemConciliacao, OcorrenciaConciliacao
from inventario import constants
from inventario.conciliacao import (
    registrar_ocorrencia,
    excluir_ocorrencia,
)
from inventario.utils_conciliacao.conciliacao_utils import criar_itens_conciliacao


class OcorrenciaBaseTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.ua = UnidadeAdministrativa.objects.create(
            codigo="001.0391", sigla="DRE-01", nome="DRE Teste"
        )
        grupo_gestor, _ = Group.objects.get_or_create(name=GRUPO_GESTOR_PATRIMONIO)
        cls.usuario = Usuario.objects.create_user(
            username="gestor", password="testpass123", unidade_administrativa=cls.ua
        )
        cls.usuario.groups.add(grupo_gestor)

    def criar_bem(self, numero=None):
        if not numero:
            numero = f"001.{str(BemPatrimonial.objects.count() + 1).zfill(9)}-0"
        return BemPatrimonial.objects.create(
            numero_patrimonial=numero,
            nome="Computador",
            descricao="Desc",
            valor_unitario=1500.00,
            marca="Dell",
            modelo="Latitude",
            status=bem_constants.APROVADO,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )

    def criar_conciliacao(self, fechado=False, ano=None):
        status = (
            constants.CONCILIACAO_FECHADO if fechado else constants.CONCILIACAO_EM_ABERTO
        )
        if ano:
            periodo_final = datetime.date(ano, 12, 31)
        else:
            periodo_final = datetime.date.today()

        inv = ConciliacaoUA.objects.create(
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final=periodo_final,
            unidade_administrativa=self.ua,
            criado_por=self.usuario,
        )

        if fechado:
            ConciliacaoUA.objects.filter(pk=inv.pk).update(
                status=constants.CONCILIACAO_FECHADO,
                fechado_por=self.usuario,
                fechado_em=datetime.datetime.now(),
            )
            inv.refresh_from_db()

        return inv

    def criar_item(
        self,
        conciliacao,
        bem,
        situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
        divergencia="",
        observacao="",
    ):
        return ItemConciliacao.objects.create(
            conciliacao=conciliacao,
            bem=bem,
            situacao=situacao,
            divergencia=divergencia,
            observacao=observacao,
        )

    def criar_item_com_ocorrencia(
        self,
        conciliacao,
        bem,
        situacao,
        divergencia="",
        observacao="",
    ):
        item = self.criar_item(
            conciliacao,
            bem,
            situacao=situacao,
            divergencia=divergencia,
            observacao=observacao,
        )
        OcorrenciaConciliacao.objects.create(
            item=item,
            situacao=situacao,
            divergencia=divergencia,
            observacao=observacao,
            registrado_por=self.usuario,
        )
        return item

    def criar_cenario_basico(self):
        conciliacao = self.criar_conciliacao()
        bem = self.criar_bem()
        item = self.criar_item(conciliacao, bem)
        return conciliacao, bem, item


class RegistrarOcorrenciaTest(OcorrenciaBaseTest):

    def test_nao_encontrado_bloqueia_bem_e_impede_movimentacao(self):
        _, bem, item = self.criar_cenario_basico()
        self.assertTrue(bem.pode_solicitar_movimentacao)

        ocorrencia = registrar_ocorrencia(
            item=item,
            situacao=constants.NAO_ENCONTRADO,
            observacao="Bem não localizado",
            usuario=self.usuario,
        )

        item.refresh_from_db()
        bem.refresh_from_db()

        self.assertEqual(ocorrencia.situacao, constants.NAO_ENCONTRADO)
        self.assertEqual(item.situacao, constants.NAO_ENCONTRADO)
        self.assertTrue(bem.bloqueado_conciliacao)
        self.assertFalse(bem.pode_solicitar_movimentacao)

    def test_divergente_exige_campo_divergencia(self):
        _, bem, item = self.criar_cenario_basico()

        with self.assertRaises(ValidationError) as ctx:
            registrar_ocorrencia(
                item=item,
                situacao=constants.DIVERGENTE,
                divergencia="",
                usuario=self.usuario,
            )
        self.assertIn("obrigatório", str(ctx.exception))

        ocorrencia = registrar_ocorrencia(
            item=item,
            situacao=constants.DIVERGENTE,
            divergencia="Marca diferente",
            usuario=self.usuario,
        )

        item.refresh_from_db()
        bem.refresh_from_db()

        self.assertEqual(item.situacao, constants.DIVERGENTE)
        self.assertEqual(item.divergencia, "Marca diferente")
        self.assertEqual(ocorrencia.divergencia, "Marca diferente")
        self.assertFalse(bem.bloqueado_conciliacao)

    def test_baixa_fisica_desbloqueia_bem(self):
        _, bem, item = self.criar_cenario_basico()
        bem.bloqueado_conciliacao = True
        bem.save()

        ocorrencia = registrar_ocorrencia(
            item=item,
            situacao=constants.BAIXA_FISICA,
            observacao="Equipamento danificado",
            usuario=self.usuario,
        )

        bem.refresh_from_db()
        self.assertEqual(ocorrencia.situacao, constants.BAIXA_FISICA)
        self.assertFalse(bem.bloqueado_conciliacao)

    def test_editar_ocorrencia_atualiza_ao_inves_de_criar_nova(self):
        _, bem, item = self.criar_cenario_basico()

        # Registra primeira ocorrência
        registrar_ocorrencia(
            item=item,
            situacao=constants.BAIXA_FISICA,
            observacao="Equipamento danificado",
            usuario=self.usuario,
        )
        self.assertEqual(item.ocorrencias.count(), 1)

        # "Edita" para outra situação - deve ATUALIZAR, não criar nova
        registrar_ocorrencia(
            item=item,
            situacao=constants.NAO_ENCONTRADO,
            observacao="Na verdade está perdido",
            usuario=self.usuario,
        )

        item.refresh_from_db()
        # Ainda deve ter apenas 1 ocorrência (atualizada)
        self.assertEqual(item.ocorrencias.count(), 1)
        self.assertEqual(item.situacao, constants.NAO_ENCONTRADO)

        ocorrencia = item.ocorrencias.first()
        self.assertEqual(ocorrencia.situacao, constants.NAO_ENCONTRADO)
        self.assertEqual(ocorrencia.observacao, "Na verdade está perdido")

        # Ao excluir, deve voltar para o estado inicial (sem ocorrência)
        excluir_ocorrencia(item=item, usuario=self.usuario)
        item.refresh_from_db()
        self.assertEqual(item.ocorrencias.count(), 0)
        self.assertEqual(item.situacao, constants.ENCONTRADO_SEM_DIVERGENCIA)

    def test_conciliacao_fechado_nao_permite_alteracoes(self):
        conciliacao = self.criar_conciliacao(fechado=True)
        bem = self.criar_bem()
        item = self.criar_item(conciliacao, bem)

        with self.assertRaises(ValidationError) as ctx:
            registrar_ocorrencia(
                item=item, situacao=constants.NAO_ENCONTRADO, usuario=self.usuario
            )
        self.assertIn("fechado", str(ctx.exception))


class ExcluirOcorrenciaTest(OcorrenciaBaseTest):

    def test_excluir_ocorrencia_deleta_e_reseta_para_padrao(self):
        _, bem, item = self.criar_cenario_basico()

        registrar_ocorrencia(
            item=item,
            situacao=constants.NAO_ENCONTRADO,
            observacao="Obs teste",
            usuario=self.usuario,
        )
        bem.refresh_from_db()
        self.assertTrue(bem.bloqueado_conciliacao)

        excluir_ocorrencia(item=item, usuario=self.usuario)

        item.refresh_from_db()
        bem.refresh_from_db()

        self.assertEqual(item.ocorrencias.count(), 0)
        self.assertEqual(item.situacao, constants.ENCONTRADO_SEM_DIVERGENCIA)
        self.assertEqual(item.observacao, "")
        self.assertEqual(item.divergencia, "")
        self.assertFalse(bem.bloqueado_conciliacao)

    def test_excluir_sem_ocorrencia_falha(self):
        _, _, item = self.criar_cenario_basico()

        with self.assertRaises(ValidationError) as ctx:
            excluir_ocorrencia(item=item, usuario=self.usuario)
        self.assertIn("não tem ocorrência", str(ctx.exception))

    def test_excluir_restaura_divergencia_herdada(self):
        inv_anterior = self.criar_conciliacao(fechado=True, ano=2020)
        bem = self.criar_bem()
        self.criar_item_com_ocorrencia(
            inv_anterior,
            bem,
            situacao=constants.DIVERGENTE,
            divergencia="Número de série não confere",
        )

        inv_novo = self.criar_conciliacao(ano=2021)
        criar_itens_conciliacao(inv_novo)

        item_novo = inv_novo.itens.get(bem=bem)
        self.assertEqual(item_novo.situacao, constants.DIVERGENTE)
        self.assertEqual(item_novo.divergencia, "Número de série não confere")

        registrar_ocorrencia(
            item=item_novo,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
            observacao="Divergência corrigida",
            usuario=self.usuario,
        )
        item_novo.refresh_from_db()
        self.assertEqual(item_novo.divergencia, "")

        excluir_ocorrencia(item=item_novo, usuario=self.usuario)

        item_novo.refresh_from_db()
        self.assertEqual(item_novo.situacao, constants.DIVERGENTE)
        self.assertEqual(item_novo.divergencia, "Número de série não confere")


class HerancaSituacaoTest(OcorrenciaBaseTest):

    def test_primeiro_conciliacao_itens_com_situacao_padrao(self):
        conciliacao = self.criar_conciliacao()
        for _ in range(3):
            self.criar_bem()

        criar_itens_conciliacao(conciliacao)

        for item in conciliacao.itens.all():
            self.assertEqual(item.situacao, constants.ENCONTRADO_SEM_DIVERGENCIA)
            self.assertFalse(item.pode_marcar_como_encontrado)

    def test_heranca_nao_encontrado(self):
        inv_anterior = self.criar_conciliacao(fechado=True, ano=2024)
        bem = self.criar_bem()
        self.criar_item_com_ocorrencia(
            inv_anterior, bem, situacao=constants.NAO_ENCONTRADO
        )

        inv_novo = self.criar_conciliacao(ano=2025)
        criar_itens_conciliacao(inv_novo)

        item_novo = inv_novo.itens.get(bem=bem)
        self.assertEqual(item_novo.situacao, constants.NAO_ENCONTRADO)
        self.assertTrue(item_novo.pode_marcar_como_encontrado)

    def test_heranca_divergente_com_texto(self):
        inv_anterior = self.criar_conciliacao(fechado=True, ano=2024)
        bem = self.criar_bem()
        self.criar_item_com_ocorrencia(
            inv_anterior,
            bem,
            situacao=constants.DIVERGENTE,
            divergencia="Número de série diferente",
        )

        inv_novo = self.criar_conciliacao(ano=2025)
        criar_itens_conciliacao(inv_novo)

        item_novo = inv_novo.itens.get(bem=bem)
        self.assertEqual(item_novo.situacao, constants.DIVERGENTE)
        self.assertEqual(item_novo.divergencia, "Número de série diferente")

    def test_heranca_baixa_fisica_e_encontrado(self):
        inv_anterior = self.criar_conciliacao(fechado=True, ano=2024)
        bem1 = self.criar_bem()
        self.criar_item_com_ocorrencia(
            inv_anterior, bem1, situacao=constants.BAIXA_FISICA
        )

        bem2 = self.criar_bem()
        self.criar_item_com_ocorrencia(
            inv_anterior, bem2, situacao=constants.ENCONTRADO
        )

        inv_novo = self.criar_conciliacao(ano=2025)
        criar_itens_conciliacao(inv_novo)

        item_baixa = inv_novo.itens.get(bem=bem1)
        self.assertEqual(item_baixa.situacao, constants.BAIXA_FISICA)

        item_encontrado = inv_novo.itens.get(bem=bem2)
        self.assertEqual(item_encontrado.situacao, constants.ENCONTRADO_SEM_DIVERGENCIA)

    def test_heranca_ignora_conciliacao_aberto(self):
        inv_aberto = self.criar_conciliacao(fechado=False, ano=2024)
        bem = self.criar_bem()
        self.criar_item_com_ocorrencia(
            inv_aberto, bem, situacao=constants.NAO_ENCONTRADO
        )

        inv_novo = self.criar_conciliacao(ano=2025)
        criar_itens_conciliacao(inv_novo)

        item_novo = inv_novo.itens.get(bem=bem)
        self.assertEqual(item_novo.situacao, constants.ENCONTRADO_SEM_DIVERGENCIA)


class PropertiesItemConciliacaoTest(OcorrenciaBaseTest):

    def test_pode_marcar_como_encontrado(self):
        conciliacao = self.criar_conciliacao()

        cenarios = [
            (constants.NAO_ENCONTRADO, True),
            (constants.ENCONTRADO_SEM_DIVERGENCIA, False),
            (constants.DIVERGENTE, False),
            (constants.BAIXA_FISICA, False),
        ]

        for situacao, esperado in cenarios:
            with self.subTest(situacao=situacao):
                bem = self.criar_bem()
                item = self.criar_item(conciliacao, bem, situacao=situacao)
                self.assertEqual(item.pode_marcar_como_encontrado, esperado)

        bem = self.criar_bem()
        item = self.criar_item(conciliacao, bem, situacao=constants.NAO_ENCONTRADO)
        self.assertTrue(item.pode_marcar_como_encontrado)

        registrar_ocorrencia(
            item=item,
            situacao=constants.DIVERGENTE,
            divergencia="Teste",
            usuario=self.usuario,
        )
        item.refresh_from_db()
        self.assertFalse(item.pode_marcar_como_encontrado)

    def test_pode_resolver_situacao(self):
        conciliacao = self.criar_conciliacao()

        cenarios = [
            (constants.DIVERGENTE, True),
            (constants.NAO_ENCONTRADO, False),  # usa pode_marcar_como_encontrado
            (constants.BAIXA_FISICA, False),  # status final
            (constants.ENCONTRADO_SEM_DIVERGENCIA, False),  # não precisa resolução
        ]

        for situacao, esperado in cenarios:
            with self.subTest(situacao=situacao):
                bem = self.criar_bem()
                item = self.criar_item(conciliacao, bem, situacao=situacao)
                self.assertEqual(item.pode_resolver_situacao, esperado)

        bem = self.criar_bem()
        item = self.criar_item(conciliacao, bem, situacao=constants.DIVERGENTE)
        registrar_ocorrencia(
            item=item, situacao=constants.NAO_ENCONTRADO, usuario=self.usuario
        )
        item.refresh_from_db()
        self.assertFalse(item.pode_resolver_situacao)

    def test_permite_registrar_ocorrencia(self):
        conciliacao = self.criar_conciliacao()

        cenarios = [
            (constants.ENCONTRADO_SEM_DIVERGENCIA, True),
            (constants.NAO_ENCONTRADO, True),
            (constants.DIVERGENTE, True),
        ]

        for situacao, esperado in cenarios:
            with self.subTest(situacao=situacao):
                bem = self.criar_bem()
                item = self.criar_item(conciliacao, bem, situacao=situacao)
                self.assertEqual(item.permite_registrar_ocorrencia, esperado)

        # BAIXA_FISICA herdada (sem ocorrência) - não permite
        bem = self.criar_bem()
        item_herdado = self.criar_item(conciliacao, bem, situacao=constants.BAIXA_FISICA)
        self.assertFalse(item_herdado.permite_registrar_ocorrencia)

        # BAIXA_FISICA registrada neste inventário (com ocorrência) - permite editar
        bem2 = self.criar_bem()
        item_registrado = self.criar_item(conciliacao, bem2)
        registrar_ocorrencia(
            item=item_registrado,
            situacao=constants.BAIXA_FISICA,
            usuario=self.usuario,
        )
        item_registrado.refresh_from_db()
        self.assertTrue(item_registrado.permite_registrar_ocorrencia)

    def test_tem_ocorrencia_verifica_registros(self):
        conciliacao = self.criar_conciliacao()
        bem = self.criar_bem()
        item = self.criar_item(conciliacao, bem, situacao=constants.NAO_ENCONTRADO)

        # Mesmo com situação diferente, não tem ocorrência (foi herdado)
        self.assertFalse(item.tem_ocorrencia)

        registrar_ocorrencia(
            item=item, situacao=constants.ENCONTRADO, usuario=self.usuario
        )
        item.refresh_from_db()
        self.assertTrue(item.tem_ocorrencia)


class ValidacoesModelTest(OcorrenciaBaseTest):

    def test_divergencia_obrigatoria_quando_divergente(self):
        _, _, item = self.criar_cenario_basico()
        item.situacao = constants.DIVERGENTE
        item.divergencia = ""

        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_divergencia_apenas_quando_divergente(self):
        _, _, item = self.criar_cenario_basico()
        item.situacao = constants.NAO_ENCONTRADO
        item.divergencia = "Não deveria ter divergência"

        with self.assertRaises(ValidationError):
            item.full_clean()


class FluxoCompletoTest(OcorrenciaBaseTest):

    def test_fluxo_bem_perdido_e_encontrado(self):
        """
        Cenário:
        1. Inv 2024: Bem marcado como NAO_ENCONTRADO
        2. Inv 2025: Herda NAO_ENCONTRADO, operador marca como ENCONTRADO
        3. Inv 2026: Deve herdar como ENCONTRADO_SEM_DIVERGENCIA
        """
        bem = self.criar_bem()

        # Inventário 2024 - bem não encontrado
        inv_2024 = self.criar_conciliacao(ano=2024)
        item_2024 = self.criar_item(inv_2024, bem)
        registrar_ocorrencia(
            item=item_2024, situacao=constants.NAO_ENCONTRADO, usuario=self.usuario
        )
        ConciliacaoUA.objects.filter(pk=inv_2024.pk).update(
            status=constants.CONCILIACAO_FECHADO,
            fechado_por=self.usuario,
            fechado_em=datetime.datetime.now(),
        )

        # Inventário 2025 - herda NAO_ENCONTRADO, operador encontra
        inv_2025 = self.criar_conciliacao(ano=2025)
        criar_itens_conciliacao(inv_2025)
        item_2025 = inv_2025.itens.get(bem=bem)

        self.assertEqual(item_2025.situacao, constants.NAO_ENCONTRADO)
        self.assertTrue(item_2025.pode_marcar_como_encontrado)

        registrar_ocorrencia(
            item=item_2025, situacao=constants.ENCONTRADO, usuario=self.usuario
        )
        ConciliacaoUA.objects.filter(pk=inv_2025.pk).update(
            status=constants.CONCILIACAO_FECHADO,
            fechado_por=self.usuario,
            fechado_em=datetime.datetime.now(),
        )

        bem.refresh_from_db()
        self.assertFalse(bem.bloqueado_conciliacao)

        # Inventário 2026 - ENCONTRADO reseta para ENCONTRADO_SEM_DIVERGENCIA
        inv_2026 = self.criar_conciliacao(ano=2026)
        criar_itens_conciliacao(inv_2026)
        item_2026 = inv_2026.itens.get(bem=bem)

        self.assertEqual(item_2026.situacao, constants.ENCONTRADO_SEM_DIVERGENCIA)
        self.assertFalse(item_2026.pode_marcar_como_encontrado)

    def test_resolver_divergencia_para_encontrado_sem_divergencia(self):
        conciliacao = self.criar_conciliacao()
        bem = self.criar_bem()
        item = self.criar_item(conciliacao, bem, situacao=constants.DIVERGENTE)

        self.assertTrue(item.pode_resolver_situacao)

        registrar_ocorrencia(
            item=item,
            situacao=constants.ENCONTRADO_SEM_DIVERGENCIA,
            observacao="Divergência corrigida no cadastro do bem",
            usuario=self.usuario,
        )

        item.refresh_from_db()
        self.assertEqual(item.situacao, constants.ENCONTRADO_SEM_DIVERGENCIA)
        self.assertTrue(item.tem_ocorrencia)
