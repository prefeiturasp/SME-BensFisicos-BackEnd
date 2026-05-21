from django.contrib import admin
from django.utils import timezone

from bem_patrimonial import constants


def _normalizar_bool_param(value):
    if value in (None, ""):
        return "0"
    value_str = str(value).strip().lower()
    return "1" if value_str in {"1", "true", "on", "yes", "sim"} else "0"


class BaixadosMaisDeUmPeriodoFilter(admin.SimpleListFilter):
    title = ""
    parameter_name = "baixados_mais_de_um_periodo"
    template = "admin/bem_patrimonial/filters/checkbox_baixados_periodo.html"

    def __init__(self, request, params, model, model_admin):
        ano_corrente = timezone.localdate().year
        self.title = f"Baixados antes de {ano_corrente - 1}"
        super().__init__(request, params, model, model_admin)
        self.other_parameter_name = "busca_geral_todas_uos"
        self.other_parameter_value = _normalizar_bool_param(
            request.GET.get(self.other_parameter_name, "0")
        )

    def lookups(self, request, model_admin):
        return (
            ("1", "Marcado"),
        )

    def queryset(self, request, queryset):
        if _normalizar_bool_param(self.value()) != "1":
            return queryset

        ano_corrente = timezone.localdate().year
        ano_limite = ano_corrente - 1

        return queryset.filter(
            status=constants.BAIXA_FISICA,
            baixa_data__year__lt=ano_limite,
        )

class BuscaGeralTodasUOsFilter(admin.SimpleListFilter):
    title = "Busca geral em todas as UOs"
    parameter_name = "busca_geral_todas_uos"
    template = "admin/bem_patrimonial/filters/checkbox_baixados_periodo.html"

    def lookups(self, request, model_admin):
        return (("1", "Marcado"),)

    def __init__(self, request, params, model, model_admin):
        super().__init__(request, params, model, model_admin)
        self.other_parameter_name = "baixados_mais_de_um_periodo"
        self.other_parameter_value = _normalizar_bool_param(
            request.GET.get(self.other_parameter_name, "0")
        )

    def queryset(self, request, queryset):
        return queryset
