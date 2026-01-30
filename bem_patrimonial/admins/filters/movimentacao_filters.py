from datetime import timedelta

from django.contrib import admin
from django.utils import timezone

from bem_patrimonial import constants


class MovimentacaoAtrasadaFilter(admin.SimpleListFilter):
    title = "Atraso"
    parameter_name = "atrasada"

    def lookups(self, request, model_admin):
        return (("1", "Sim"),)

    def queryset(self, request, queryset):
        if self.value() == "1":
            limite = timezone.now() - timedelta(days=7)
            return queryset.filter(
                status=constants.ENVIADA,
                criado_em__lte=limite,
            )
        return queryset
