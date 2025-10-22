from django.contrib import admin
from dados_comuns.libs.unidade_administrativa import uas_do_usuario
from dados_comuns.models import UnidadeAdministrativa

UNIDADE_ADMINISTRATIVA_ORIGEM_AUTOCOMPLETE = "unidade_administrativa_origem"


@admin.register(UnidadeAdministrativa)
class UnidadeAdministrativaAdmin(admin.ModelAdmin):
    search_fields = [
        "nome",
        "sigla",
        "codigo",
    ]

    def get_search_results(self, request, queryset, search_term):
        """
        Filtra o autocomplete para exibir apenas as UAs associadas ao usuário Operador.
        """
        queryset, use_distinct = super().get_search_results(
            request, queryset, search_term
        )

        field_name = request.GET.get("field_name")
        if (
            field_name == UNIDADE_ADMINISTRATIVA_ORIGEM_AUTOCOMPLETE
            and request.user.is_operador_inventario
        ):
            uas_user = uas_do_usuario(request.user)
            queryset = queryset.filter(id__in=uas_user.values_list("id", flat=True))

        return queryset, use_distinct
