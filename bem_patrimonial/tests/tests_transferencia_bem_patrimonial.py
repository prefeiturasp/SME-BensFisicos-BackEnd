from django.core.exceptions import ValidationError
from django.test import TestCase

from bem_patrimonial import constants
from bem_patrimonial.models import (
    BemPatrimonial,
    StatusBemPatrimonial,
    TransferenciaBemPatrimonial,
    TransferenciaBensItem,
)
from dados_comuns.tests.auth_test_utils import auth_kwargs, codigo_ua, codigo_uo
from dados_comuns.tests.factories import criar_ua, criar_uo
from usuario.models import Usuario


class TransferenciaBemPatrimonialModelTestCase(TestCase):
    def setUp(self):
        self.uo_origem = criar_uo(
            codigo=codigo_uo(1, 16, 28),
            nome="SME",
            sigla="SME",
        )
        self.ua_origem_1 = criar_ua(
            uo=self.uo_origem,
            codigo=f"{self.uo_origem.codigo}.001",
            sigla="UA1",
            nome="Unidade 1",
        )
        self.ua_origem_2 = criar_ua(
            uo=self.uo_origem,
            codigo=f"{self.uo_origem.codigo}.002",
            sigla="UA2",
            nome="Unidade 2",
        )
        self.uo_destino = criar_uo(
            codigo=codigo_uo(2, 20, 30),
            nome="Secretaria Externa",
            sigla="EXT",
        )
        self.ua_destino = criar_ua(
            uo=self.uo_destino,
            codigo=codigo_ua(2, 20, 30, 1),
            sigla="PC",
            nome="Ponto Central",
        )
        self.gestor = Usuario.objects.create_user(
            username="gestor_transferencia",
            email="gestor.transferencia@test.com",
            **auth_kwargs("123456"),
            nome="Gestor",
            is_staff=True,
            unidade_orcamentaria=self.uo_origem,
            unidade_administrativa=self.ua_origem_1,
        )

    def _criar_bem(self, numero, ua, status=constants.APROVADO):
        return BemPatrimonial.objects.create(
            numero_patrimonial=numero,
            nome=f"Bem {numero}",
            descricao="Descrição",
            valor_unitario=100,
            marca="Marca",
            modelo="Modelo",
            numero_processo="PROC-BASE",
            status=status,
            unidade_administrativa=ua,
            criado_por=self.gestor,
        )

    def _criar_transferencia(self):
        return TransferenciaBemPatrimonial.objects.create(
            unidade_orcamentaria_origem=self.uo_origem,
            unidade_orcamentaria_destino=self.uo_destino,
            unidade_administrativa_destino=self.ua_destino,
            numero_processo="SEI-123456/2026",
            observacao="Transferência externa",
            criado_por=self.gestor,
        )

    def test_efetivar_transferencia_move_bens_e_registra_status(self):
        bem1 = self._criar_bem("001.000000001-1", self.ua_origem_1)
        bem2 = self._criar_bem("001.000000002-2", self.ua_origem_2)
        transferencia = self._criar_transferencia()

        TransferenciaBensItem.objects.create(transferencia=transferencia, bem=bem1)
        TransferenciaBensItem.objects.create(transferencia=transferencia, bem=bem2)

        transferencia.efetivar_transferencia(self.gestor)

        bem1.refresh_from_db()
        bem2.refresh_from_db()
        transferencia.refresh_from_db()

        self.assertEqual(bem1.unidade_administrativa, self.ua_destino)
        self.assertEqual(bem2.unidade_administrativa, self.ua_destino)
        self.assertEqual(bem1.status, constants.TRANSFERIDO)
        self.assertEqual(bem2.status, constants.TRANSFERIDO)
        self.assertTrue(transferencia.numero_ntbpm)
        self.assertEqual(
            StatusBemPatrimonial.objects.filter(
                bem_patrimonial=bem1,
                status=constants.TRANSFERIDO,
            ).count(),
            1,
        )

    def test_efetivar_transferencia_exige_bens(self):
        transferencia = self._criar_transferencia()

        with self.assertRaises(ValidationError) as ctx:
            transferencia.efetivar_transferencia(self.gestor)

        self.assertIn("sem bens", str(ctx.exception))

    def test_efetivar_transferencia_rejeita_bem_fora_da_uo_origem(self):
        outra_uo = criar_uo(
            codigo=codigo_uo(9, 9, 9),
            nome="Outra UO",
            sigla="OUT",
        )
        outra_ua = criar_ua(
            uo=outra_uo,
            codigo=codigo_ua(9, 9, 9, 1),
            sigla="OUT1",
            nome="Outra UA",
        )
        bem = self._criar_bem("001.000000003-3", outra_ua)
        transferencia = self._criar_transferencia()
        TransferenciaBensItem.objects.create(transferencia=transferencia, bem=bem)

        with self.assertRaises(ValidationError) as ctx:
            transferencia.efetivar_transferencia(self.gestor)

        self.assertIn("não pertence à UO de origem", str(ctx.exception))

    def test_efetivar_transferencia_rejeita_bem_nao_aprovado(self):
        bem = self._criar_bem(
            "001.000000004-4",
            self.ua_origem_1,
            status=constants.BLOQUEADO,
        )
        transferencia = self._criar_transferencia()
        TransferenciaBensItem.objects.create(transferencia=transferencia, bem=bem)

        with self.assertRaises(ValidationError) as ctx:
            transferencia.efetivar_transferencia(self.gestor)

        self.assertIn("status 'Aprovado'", str(ctx.exception))

    def test_efetivar_transferencia_revalida_bem_antes_de_gravar(self):
        bem = self._criar_bem("001.000000005-5", self.ua_origem_1)
        transferencia = self._criar_transferencia()
        TransferenciaBensItem.objects.create(transferencia=transferencia, bem=bem)

        bem.unidade_administrativa = self.ua_destino
        bem.status = constants.TRANSFERIDO
        bem.save(update_fields=["unidade_administrativa", "status", "atualizado_em"])

        with self.assertRaises(ValidationError) as ctx:
            transferencia.efetivar_transferencia(self.gestor)

        transferencia.refresh_from_db()
        self.assertIn("status 'Aprovado'", str(ctx.exception))
        self.assertFalse(transferencia.numero_ntbpm)

    def test_numero_processo_da_transferencia_pode_ser_repetido(self):
        self._criar_transferencia()
        transferencia = TransferenciaBemPatrimonial(
            unidade_orcamentaria_origem=self.uo_origem,
            unidade_orcamentaria_destino=self.uo_destino,
            unidade_administrativa_destino=self.ua_destino,
            numero_processo="SEI-123456/2026",
            observacao="Outra transferência",
            criado_por=self.gestor,
        )

        transferencia.full_clean()
        transferencia.save()

        self.assertEqual(
            TransferenciaBemPatrimonial.objects.filter(
                numero_processo="SEI-123456/2026"
            ).count(),
            2,
        )

    def test_model_permite_multiplas_transferencias_mesmo_processo(self):
        t1 = self._criar_transferencia()
        t2 = TransferenciaBemPatrimonial.objects.create(
            unidade_orcamentaria_origem=self.uo_origem,
            unidade_orcamentaria_destino=self.uo_destino,
            unidade_administrativa_destino=self.ua_destino,
            numero_processo="SEI-123456/2026",
            observacao="Segunda transferência no mesmo processo",
            criado_por=self.gestor,
        )

        self.assertEqual(t1.numero_processo, t2.numero_processo)
        self.assertNotEqual(t1.pk, t2.pk)

    def test_efetivar_transferencia_com_multiplos_processos_iguais(self):
        bem1 = self._criar_bem("001.000000006-6", self.ua_origem_1)
        bem2 = self._criar_bem("001.000000007-7", self.ua_origem_2)

        t1 = self._criar_transferencia()
        TransferenciaBensItem.objects.create(transferencia=t1, bem=bem1)
        t1.efetivar_transferencia(self.gestor)

        t2 = TransferenciaBemPatrimonial.objects.create(
            unidade_orcamentaria_origem=self.uo_origem,
            unidade_orcamentaria_destino=self.uo_destino,
            unidade_administrativa_destino=self.ua_destino,
            numero_processo="SEI-123456/2026",
            observacao="Segunda transferência no mesmo processo",
            criado_por=self.gestor,
        )
        TransferenciaBensItem.objects.create(transferencia=t2, bem=bem2)
        t2.efetivar_transferencia(self.gestor)

        bem2.refresh_from_db()
        t2.refresh_from_db()
        self.assertEqual(bem2.unidade_administrativa, self.ua_destino)
        self.assertEqual(bem2.status, constants.TRANSFERIDO)
        self.assertTrue(t2.numero_ntbpm)
        self.assertEqual(t1.numero_processo, t2.numero_processo)
        self.assertNotEqual(t1.numero_ntbpm, t2.numero_ntbpm)