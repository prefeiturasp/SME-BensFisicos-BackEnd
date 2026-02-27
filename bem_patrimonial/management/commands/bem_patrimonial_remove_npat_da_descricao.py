import re

from django.core.management.base import BaseCommand
from django.db import transaction

from bem_patrimonial.models import BemPatrimonial, NPAT_NUM_REGEX


class Command(BaseCommand):
    help = (
        "Remove o número patrimonial da descrição dos bens e limpa caracteres "
        "especiais no início da descrição."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Apenas simula as alterações, sem salvar no banco.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limita quantidade de registros processados.",
        )

    def _deve_ignorar_bem(self, bem, numero):
        if not numero:
            return False
        if bem.numero_formato_antigo or bem.sem_numeracao:
            return False
        if re.fullmatch(NPAT_NUM_REGEX, numero):
            return False
        self.stdout.write(
            self.style.WARNING(
                f"[#{bem.pk}] Número '{numero}' deveria ser formato novo "
                f"mas não bate regex. Ignorando."
            )
        )
        return True

    def _processar_descricao_bem(self, bem, numero, descricao_original):
        descricao_trabalhada = descricao_original
        alterou = False
        if numero and numero in descricao_trabalhada:
            descricao_trabalhada = descricao_trabalhada.replace(numero, "").strip()
            alterou = True
        descricao_limpa = re.sub(
            r"^[^A-Za-z0-9]+", "", descricao_trabalhada
        ).strip()
        if descricao_limpa != descricao_original:
            alterou = True
        return descricao_limpa, alterou

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        limit = options["limit"]

        qs = BemPatrimonial.objects.exclude(numero_patrimonial__isnull=True).exclude(
            numero_patrimonial__exact=""
        )
        if limit:
            qs = qs[:limit]

        total_verificados = 0
        total_alterados = 0

        self.stdout.write(
            self.style.WARNING(
                f"Processando {qs.count()} bens "
                f"({'DRY RUN' if dry_run else 'EXECUÇÃO REAL'})..."
            )
        )

        with transaction.atomic():
            for bem in qs.iterator():
                total_verificados += 1
                numero = (bem.numero_patrimonial or "").strip()
                descricao_original = bem.descricao or ""

                if self._deve_ignorar_bem(bem, numero):
                    continue

                descricao_limpa, alterou = self._processar_descricao_bem(
                    bem, numero, descricao_original
                )

                if not alterou:
                    continue

                total_alterados += 1
                self.stdout.write(f"[#{bem.pk}] Ajustando descrição:")
                self.stdout.write(f"  NPAT:   {numero}")
                self.stdout.write(f"  ANTES:  {descricao_original!r}")
                self.stdout.write(f"  DEPOIS: {descricao_limpa!r}")
                self.stdout.write("")

                if not dry_run:
                    bem.descricao = descricao_limpa
                    bem.save(update_fields=["descricao", "atualizado_em"])

            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                f"Finalizado. Verificados: {total_verificados} • Alterados: {total_alterados} "
                f"{'(DRY RUN, nada salvo)' if dry_run else ''}"
            )
        )
