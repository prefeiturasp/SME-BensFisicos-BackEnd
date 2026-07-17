from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models.signals import post_save

from bem_patrimonial import constants
from bem_patrimonial.models import (
    BemPatrimonial,
    StatusBemPatrimonial,
    TransferenciaBemPatrimonial,
    TransferenciaBensItem,
    bempatrimonial_sync_conciliacao_em_aberto,
    cria_primeiro_status_bem_patrimonial,
)
from bem_patrimonial.ntbpm import gerar_numero_ntbpm
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria


class Command(BaseCommand):
    help = "Cria massa demo de transferências de bens patrimoniais para validação local."

    SOURCE_UO = {
        "codigo": "01.16.90",
        "nome": "UO DEMO TRANSFERENCIAS",
        "sigla": "UOTR",
    }
    SOURCE_UAS = (
        {
            "codigo": "01.16.90.001",
            "sigla": "UA01",
            "nome": "UA Origem 01",
        },
        {
            "codigo": "01.16.90.002",
            "sigla": "UA02",
            "nome": "UA Origem 02",
        },
    )
    DESTINOS = (
        {
            "uo": {
                "codigo": "02.20.90",
                "nome": "Secretaria Externa 01",
                "sigla": "EXT01",
            },
            "ua": {
                "codigo": "02.20.90.001",
                "sigla": "PC01",
                "nome": "Ponto Central 01",
            },
            "processo": "SEED-TRF-001/2026",
            "bens": ("900.000.001-1", "900.000.002-2"),
        },
        {
            "uo": {
                "codigo": "03.20.90",
                "nome": "Secretaria Externa 02",
                "sigla": "EXT02",
            },
            "ua": {
                "codigo": "03.20.90.001",
                "sigla": "PC02",
                "nome": "Ponto Central 02",
            },
            "processo": "SEED-TRF-002/2026",
            "bens": ("900.000.003-3", "900.000.004-4"),
        },
        {
            "uo": {
                "codigo": "04.20.90",
                "nome": "Secretaria Externa 03",
                "sigla": "EXT03",
            },
            "ua": {
                "codigo": "04.20.90.001",
                "sigla": "PC03",
                "nome": "Ponto Central 03",
            },
            "processo": "SEED-TRF-003/2026",
            "bens": ("900.000.005-5", "900.000.006-6"),
        },
    )

    def handle(self, *args, **options):
        system_user = self._obter_usuario_sistema()
        self._desconectar_signals_bem()

        try:
            with transaction.atomic():
                uo_origem = self._obter_uo(self.SOURCE_UO)
                uas_origem = [self._obter_ua(uo_origem, data) for data in self.SOURCE_UAS]
                bens_por_numero = self._criar_bens_demo(system_user, uas_origem)

                transferencias_criadas = 0
                bens_disponiveis = list(bens_por_numero.values())
                indice_bem = 0

                for destino in self.DESTINOS:
                    uo_destino = self._obter_uo(destino["uo"])
                    ua_destino = self._obter_ua(uo_destino, destino["ua"])
                    transferencia, created = self._obter_ou_criar_transferencia(
                        uo_origem=uo_origem,
                        uo_destino=uo_destino,
                        ua_destino=ua_destino,
                        processo=destino["processo"],
                        criado_por=system_user,
                    )

                    if created:
                        bens_da_transferencia = bens_disponiveis[indice_bem : indice_bem + 2]
                        indice_bem += 2
                        self._vincular_bens(transferencia, bens_da_transferencia)
                        self._efetivar_transferencia_demo(transferencia, system_user)
                        transferencias_criadas += 1
                    elif self._transferencia_em_rascunho(transferencia):
                        bens_da_transferencia = bens_disponiveis[indice_bem : indice_bem + 2]
                        indice_bem += 2
                        if not transferencia.itens.exists():
                            self._vincular_bens(transferencia, bens_da_transferencia)
                        self._efetivar_transferencia_demo(transferencia, system_user)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Seed de transferências concluído: {transferencias_criadas} novas transferência(s) criadas."
                )
            )
        finally:
            self._reconectar_signals_bem()

    def _obter_usuario_sistema(self):
        user_model = get_user_model()
        usuario, created = user_model.objects.get_or_create(
            username="sistema_transfer_seed",
            defaults={
                "email": "sistema.transfer.seed@example.com",
                "nome": "Sistema Seed Transferencias",
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        if created:
            usuario.set_password("sistema_transfer_seed")
        usuario.email = usuario.email or "sistema.transfer.seed@example.com"
        usuario.nome = getattr(usuario, "nome", "") or "Sistema Seed Transferencias"
        usuario.is_staff = True
        usuario.is_superuser = True
        usuario.is_active = True
        usuario.save()
        return usuario

    def _desconectar_signals_bem(self):
        try:
            post_save.disconnect(
                receiver=cria_primeiro_status_bem_patrimonial,
                sender=BemPatrimonial,
            )
        except Exception:
            pass

        try:
            post_save.disconnect(
                receiver=bempatrimonial_sync_conciliacao_em_aberto,
                sender=BemPatrimonial,
            )
        except Exception:
            pass

    def _reconectar_signals_bem(self):
        try:
            post_save.connect(
                receiver=cria_primeiro_status_bem_patrimonial,
                sender=BemPatrimonial,
            )
        except Exception:
            pass

        try:
            post_save.connect(
                receiver=bempatrimonial_sync_conciliacao_em_aberto,
                sender=BemPatrimonial,
            )
        except Exception:
            pass

    def _obter_uo(self, payload):
        uo, _ = UnidadeOrcamentaria.objects.get_or_create(
            codigo=payload["codigo"],
            defaults={
                "nome": payload["nome"],
                "sigla": payload["sigla"],
                "sigla_orgao": payload.get("sigla_orgao", ""),
                "orgao": payload.get("orgao", ""),
                "codigo_orgao": payload.get("codigo_orgao", ""),
                "ativa": True,
            },
        )
        return uo

    def _obter_ua(self, uo, payload):
        ua, _ = UnidadeAdministrativa.objects.get_or_create(
            codigo=payload["codigo"],
            defaults={
                "unidade_orcamentaria": uo,
                "sigla": payload["sigla"],
                "nome": payload["nome"],
                "status": UnidadeAdministrativa.ATIVA,
            },
        )
        if ua.unidade_orcamentaria_id != uo.id:
            ua.unidade_orcamentaria = uo
            ua.save(update_fields=["unidade_orcamentaria", "updated_at"])
        return ua

    def _criar_bens_demo(self, criado_por, uas_origem):
        bens = {}
        bens_config = [
            ("900.000.001-1", uas_origem[0], "Bem Transferencia Demo 01"),
            ("900.000.002-2", uas_origem[0], "Bem Transferencia Demo 02"),
            ("900.000.003-3", uas_origem[1], "Bem Transferencia Demo 03"),
            ("900.000.004-4", uas_origem[1], "Bem Transferencia Demo 04"),
            ("900.000.005-5", uas_origem[0], "Bem Transferencia Demo 05"),
            ("900.000.006-6", uas_origem[1], "Bem Transferencia Demo 06"),
        ]

        for numero_patrimonial, ua, nome in bens_config:
            bem, _ = BemPatrimonial.objects.get_or_create(
                numero_patrimonial=numero_patrimonial,
                defaults={
                    "nome": nome,
                    "descricao": f"{nome} para validar transferências.",
                    "valor_unitario": Decimal("1000.00"),
                    "marca": "DEMO",
                    "modelo": "DEMO",
                    "localizacao": "Depósito",
                    "numero_processo": "SEED-TRANSFERENCIA-DEMO",
                    "status": constants.APROVADO,
                    "unidade_administrativa": ua,
                    "criado_por": criado_por,
                },
            )
            bens[numero_patrimonial] = bem

        return bens

    def _obter_ou_criar_transferencia(self, *, uo_origem, uo_destino, ua_destino, processo, criado_por):
        transferencia, created = TransferenciaBemPatrimonial.objects.get_or_create(
            unidade_orcamentaria_origem=uo_origem,
            unidade_orcamentaria_destino=uo_destino,
            unidade_administrativa_destino=ua_destino,
            numero_processo=processo,
            defaults={
                "numero_ntbpm": f"DRAFT-{processo.replace('/', '-')}",
                "observacao": "Carga de demo para validacao de transferencia.",
                "criado_por": criado_por,
            },
        )
        return transferencia, created

    def _vincular_bens(self, transferencia, bens):
        for bem in bens:
            TransferenciaBensItem.objects.get_or_create(
                transferencia=transferencia,
                bem=bem,
            )

    def _transferencia_em_rascunho(self, transferencia):
        numero_ntbpm = (transferencia.numero_ntbpm or "").strip()
        return not numero_ntbpm or numero_ntbpm.startswith("DRAFT-")

    def _efetivar_transferencia_demo(self, transferencia, usuario):
        transferencia = type(transferencia).objects.select_for_update().get(pk=transferencia.pk)

        transferencia._validar_destino()
        itens = transferencia._obter_itens_para_efetivar()
        transferencia._validar_bens(itens)

        observacao_status = (
            f"Transferência concluída para {transferencia.unidade_orcamentaria_destino} "
            f"(processo {transferencia.numero_processo})."
        )

        for item in itens:
            bem = item.bem
            bem.unidade_administrativa = transferencia.unidade_administrativa_destino
            bem.status = constants.TRANSFERIDO
            bem.save(update_fields=["unidade_administrativa", "status", "atualizado_em"])

            StatusBemPatrimonial.objects.create(
                bem_patrimonial=bem,
                status=constants.TRANSFERIDO,
                atualizado_por=usuario,
                observacao=observacao_status,
            )

        transferencia.numero_ntbpm = gerar_numero_ntbpm(transferencia)
        transferencia.save(
            update_fields=[
                "numero_ntbpm",
                "atualizado_em",
            ]
        )
        transferencia.refresh_from_db()
