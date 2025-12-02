from django.contrib import admin


class SemNumeroFilter(admin.SimpleListFilter):
    title = "Sem número"
    parameter_name = "sem_numero"

    def lookups(self, request, model_admin):
        return (("1", "Somente bens sem número"),)

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.filter(sem_numeracao=True)
        return queryset
