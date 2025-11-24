from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from bem_patrimonial.models import MovimentacaoBemPatrimonial
from bem_patrimonial.cimbpm import gerar_numero_cimbpm


class Command(BaseCommand):
    help = "Gera números CIMBPM para movimentações sem número"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limpar",
            action="store_true",
            help="Limpa números existentes antes de gerar",
        )

    def handle(self, *args, **options):
        if options["limpar"]:
            self._limpar_numeros()

        movimentacoes = MovimentacaoBemPatrimonial.objects.filter(
            Q(numero_cimbpm__isnull=True) | Q(numero_cimbpm="")
        ).order_by("criado_em", "id")

        total = movimentacoes.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nenhuma movimentação pendente"))
            return

        processados = 0
        erros = 0

        for mov in movimentacoes:
            try:
                with transaction.atomic():
                    mov.numero_cimbpm = gerar_numero_cimbpm(mov)
                    mov.save(update_fields=["numero_cimbpm"])
                processados += 1
            except Exception as e:
                erros += 1
                self.stdout.write(self.style.ERROR(f"Erro ID {mov.id}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"{processados} processados"))
        if erros > 0:
            self.stdout.write(self.style.ERROR(f"{erros} erros"))

    def _limpar_numeros(self):
        total = MovimentacaoBemPatrimonial.objects.filter(
            numero_cimbpm__isnull=False
        ).count()

        MovimentacaoBemPatrimonial.objects.filter(numero_cimbpm__isnull=False).update(
            numero_cimbpm=None, documento_cimbpm=""
        )

        self.stdout.write(self.style.SUCCESS(f"{total} números limpos"))
