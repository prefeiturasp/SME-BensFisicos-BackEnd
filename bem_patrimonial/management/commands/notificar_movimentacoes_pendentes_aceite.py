from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from bem_patrimonial import constants
from bem_patrimonial.emails import envia_email_movimentacoes_pendentes_aceite
from bem_patrimonial.models import MovimentacaoBemPatrimonial
from usuario.constants import GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario


class Command(BaseCommand):
    help = (
        "Envia e-mail semanal para gestores e operadores das UAs de destino "
        "com movimentações pendentes de aceite há mais de 7 dias."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dias-minimo",
            type=int,
            default=7,
            help="Quantidade mínima de dias para considerar pendência.",
        )
        parser.add_argument(
            "--dias-urgente",
            type=int,
            default=30,
            help="Quantidade de dias para marcar pendência como urgente.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Apenas simula o envio e imprime UAs/destinatários.",
        )
        parser.add_argument(
            "--ua-id",
            type=int,
            default=None,
            help="Filtra envio para uma UA específica (ID).",
        )
        parser.add_argument(
            "--ua-codigo",
            type=str,
            default=None,
            help="Filtra envio para uma UA específica (código).",
        )
        parser.add_argument(
            "--log-file",
            type=str,
            default=None,
            help="Caminho do arquivo de log para salvar o resumo.",
        )

    def handle(self, *args, **options):
        dias_minimo = options["dias_minimo"]
        dias_urgente = options["dias_urgente"]
        dry_run = options["dry_run"]
        ua_id = options["ua_id"]
        ua_codigo = options["ua_codigo"]
        log_file = options["log_file"]

        limite = timezone.now() - timedelta(days=dias_minimo)

        movimentacoes = (
            MovimentacaoBemPatrimonial.objects.filter(
                status=constants.ENVIADA,
                criado_em__lte=limite,
            )
            .select_related(
                "unidade_administrativa_origem",
                "unidade_administrativa_destino",
            )
            .prefetch_related("itens__bem")
        )

        if ua_id:
            movimentacoes = movimentacoes.filter(
                unidade_administrativa_destino_id=ua_id
            )

        if ua_codigo:
            movimentacoes = movimentacoes.filter(
                unidade_administrativa_destino__codigo=ua_codigo
            )

        if not movimentacoes.exists():
            self.stdout.write(self.style.SUCCESS("Nenhuma movimentação pendente."))
            return

        movimentacoes_por_ua = {}
        for mov in movimentacoes:
            ua_destino = mov.unidade_administrativa_destino
            movimentacoes_por_ua.setdefault(ua_destino, []).append(mov)

        total_emails = 0
        total_ua = len(movimentacoes_por_ua)
        total_sem_email = 0
        linhas_log = []
        for ua, movs in movimentacoes_por_ua.items():
            usuarios = (
                Usuario.objects.filter(
                    is_active=True,
                    unidade_administrativa=ua,
                )
                .filter(
                    Q(groups__name=GRUPO_GESTOR_PATRIMONIO)
                    | Q(groups__name=GRUPO_OPERADOR_INVENTARIO)
                )
                .distinct()
                .only("email")
            )

            emails = [u.email for u in usuarios if u.email]
            ua_label = f"{getattr(ua, 'codigo', '')} - {ua.nome}".strip(" -")
            if not emails:
                total_sem_email += 1
                msg = (
                    f"UA: {ua_label} | Movimentações: {len(movs)} | "
                    "Destinatários: 0 | NÃO ENVIADO (sem e-mail)"
                )
                self.stdout.write(self.style.WARNING(msg))
                linhas_log.append(msg)
                continue

            if dry_run:
                msg = (
                    f"[SIMULAÇÃO] UA: {ua_label} | Movimentações: {len(movs)} | "
                    f"Destinatários: {len(emails)} | Emails: {', '.join(emails)}"
                )
                self.stdout.write(self.style.WARNING(msg))
                linhas_log.append(msg)
            else:
                envia_email_movimentacoes_pendentes_aceite(
                    ua,
                    movs,
                    emails,
                    dias_minimo=dias_minimo,
                    dias_urgente=dias_urgente,
                )
                total_emails += 1
                msg = (
                    f"UA: {ua_label} | Movimentações: {len(movs)} | "
                    f"Destinatários: {len(emails)} | Emails: {', '.join(emails)}"
                )
                self.stdout.write(self.style.SUCCESS(msg))
                linhas_log.append(msg)

        if dry_run:
            uas_com_destinatarios = sum(
                1
                for ua, _ in movimentacoes_por_ua.items()
                if Usuario.objects.filter(is_active=True, unidade_administrativa=ua)
                .filter(
                    Q(groups__name=GRUPO_GESTOR_PATRIMONIO)
                    | Q(groups__name=GRUPO_OPERADOR_INVENTARIO)
                )
                .exclude(email="")
                .exists()
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"[SIMULAÇÃO] UAs com pendências: {total_ua}. "
                    f"UAs com destinatários: {uas_com_destinatarios}. "
                    f"UAs sem e-mail: {total_sem_email}."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"UAs com pendências: {total_ua}. "
                    f"E-mails enviados para {total_emails} unidade(s) administrativa(s). "
                    f"UAs sem e-mail: {total_sem_email}."
                )
            )

        if log_file and linhas_log:
            with open(log_file, "a", encoding="utf-8") as arquivo:
                arquivo.write("\n".join(linhas_log) + "\n")
