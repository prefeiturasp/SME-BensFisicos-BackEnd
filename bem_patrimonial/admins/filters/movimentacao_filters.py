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


class IntervaloNpDeFilter(admin.SimpleListFilter):
    """
    Filtro responsável pelo campo 'De' e pela renderização do formulário.
    Declarar np_de como parameter_name faz o Django Admin preservar
    esse parâmetro na URL entre requisições.
    """

    title = "Por Intervalo"
    parameter_name = "np_de"
    template = "admin/bem_patrimonial/filters/intervalo_numero_patrimonial.html"

    def lookups(self, request, model_admin):
        return ()

    def has_output(self):
        return True

    def choices(self, changelist):
        # Necessário retornar ao menos um item para o template ser renderizado
        yield {}

    def queryset(self, request, queryset):
        np_de = request.GET.get("np_de", "").strip()
        np_ate = request.GET.get("np_ate", "").strip()

        if not np_de and not np_ate:
            return queryset

        if np_de:
            queryset = queryset.filter(
                itens__bem__numero_patrimonial__gte=np_de
            )
        if np_ate:
            queryset = queryset.filter(
                itens__bem__numero_patrimonial__lte=np_ate
            )

        return queryset.distinct()


class IntervaloNpAteFilter(admin.SimpleListFilter):
    """
    Filtro fantasma — apenas declara np_ate como parameter_name para
    que o Django Admin não descarte esse parâmetro da URL.
    Não renderiza nada (template vazio) e não aplica queryset próprio
    (a filtragem real está em IntervaloNpDeFilter).
    """

    title = ""
    parameter_name = "np_ate"
    template = "admin/bem_patrimonial/filters/filtro_vazio.html"

    def lookups(self, request, model_admin):
        return ()

    def has_output(self):
        # Não renderiza bloco visual na barra lateral
        return False

    def queryset(self, request, queryset):
        # A filtragem é feita inteiramente em IntervaloNpDeFilter
        return queryset
