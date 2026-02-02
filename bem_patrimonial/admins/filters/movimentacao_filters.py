from datetime import timedelta

from django.contrib import admin
from django.utils import timezone

from bem_patrimonial import constants


class MovimentacaoAtrasadaFilter(admin.SimpleListFilter):
    title = "Movimentação atrasada"
    parameter_name = "atrasada"

    def lookups(self, request, model_admin):
        return (("1", "Sim"), ("0", "Não"))

    def choices(self, changelist):
        yield {
            "selected": self.value() in (None, "0"),
            "query_string": changelist.get_query_string({self.parameter_name: "0"}),
            "display": "Não",
        }
        yield {
            "selected": self.value() == "1",
            "query_string": changelist.get_query_string({self.parameter_name: "1"}),
            "display": "Sim",
        }

    def queryset(self, request, queryset):
        if self.value() == "1":
            limite = timezone.now() - timedelta(days=7)
            return queryset.filter(
                status=constants.ENVIADA,
                criado_em__lte=limite,
            )
        return queryset
