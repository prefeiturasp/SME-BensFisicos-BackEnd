from django.contrib import admin
from django.utils import timezone

from bem_patrimonial import constants


class BaixadosMaisDeUmPeriodoFilter(admin.SimpleListFilter):
    title = ""
    parameter_name = "baixados_mais_de_um_periodo"
    template = "admin/bem_patrimonial/filters/checkbox_baixados_periodo.html"

    def __init__(self, request, params, model, model_admin):
        ano_corrente = timezone.localdate().year
        self.title = f"Baixados antes de {ano_corrente - 1}"
        super().__init__(request, params, model, model_admin)

    def lookups(self, request, model_admin):
        return (
            ("1", "Marcado"),
        )

    def queryset(self, request, queryset):
        if self.value() != "1":
            return queryset

        ano_corrente = timezone.localdate().year
        ano_limite = ano_corrente - 1

        return queryset.filter(
            status=constants.BAIXA_FISICA,
            baixa_data__year__lt=ano_limite,
        )
