from django.contrib import admin
from django.utils import timezone

from bem_patrimonial import constants


class BaixadosMaisDeUmPeriodoFilter(admin.SimpleListFilter):
    title = "Baixados a mais de um período"
    parameter_name = "baixados_mais_de_um_periodo"

    def lookups(self, request, model_admin):
        return (
            ("1", "Sim"),
            ("0", "Não"),
        )

    def queryset(self, request, queryset):
        val = self.value()
        if val not in ("0", "1"):
            return queryset

        ano_corrente = timezone.localdate().year
        ano_minimo_visivel = ano_corrente - 1  # período = ano anterior ao corrente

        # depende de queryset já anotado com "baixa_data"
        if val == "1":
            # antigos (antes do período)
            return queryset.filter(
                status=constants.BAIXA_FISICA,
                baixa_data__year__lt=ano_minimo_visivel,
            )

        # do período em diante (2025 e 2026 quando corrente=2026)
        return queryset.filter(
            status=constants.BAIXA_FISICA,
            baixa_data__year__gte=ano_minimo_visivel,
        )
