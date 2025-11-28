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
                alterou = False

                numero = (bem.numero_patrimonial or "").strip()
                descricao_original = bem.descricao or ""
                descricao_trabalhada = descricao_original

                if numero:
                    # REGRAS DE SEGURANÇA
                    if not bem.numero_formato_antigo and not bem.sem_numeracao:
                        # Deve estar no formato novo
                        if not re.fullmatch(NPAT_NUM_REGEX, numero):
                            self.stdout.write(
                                self.style.WARNING(
                                    f"[#{bem.pk}] Número '{numero}' deveria ser formato novo "
                                    f"mas não bate regex. Ignorando."
                                )
                            )
                            continue

                    # REMOVE NPAT DA DESCRIÇÃO
                    if numero in descricao_trabalhada:
                        descricao_trabalhada = descricao_trabalhada.replace(
                            numero, ""
                        ).strip()
                        alterou = True

                # NOVA REGRA: remover caracteres especiais no início
                descricao_limpa = re.sub(
                    r"^[^A-Za-z0-9]+", "", descricao_trabalhada
                ).strip()

                if descricao_limpa != descricao_original:
                    alterou = True

                if alterou:
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
