from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from dados_comuns.libs.unidade_administrativa import uas_do_usuario
from dados_comuns.models import UnidadeAdministrativa

UNIDADE_ADMINISTRATIVA_ORIGEM_AUTOCOMPLETE = "unidade_administrativa_origem"


class StatusFilter(admin.SimpleListFilter):
    title = "Status"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return UnidadeAdministrativa.STATUS_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


@admin.register(UnidadeAdministrativa)
class UnidadeAdministrativaAdmin(admin.ModelAdmin):
    list_display = (
        "codigo",
        "sigla",
        "nome",
    )
    search_fields = (
        "sigla",
        "nome",
        "codigo",
    )
    search_help_text = "Pesquise por sigla, nome ou código."
    ordering = ("codigo", "sigla", "nome")

    list_filter = [StatusFilter]

    fields = [
        "codigo",
        "sigla",
        "nome",
        "status",
    ]

    def get_queryset(self, request):
        # Retorna queryset sem filtro - deixa o StatusFilter controlar tudo.
        return super().get_queryset(request)

    def get_search_results(self, request, queryset, search_term):
        """
        Filtra o autocomplete para exibir apenas as UAs associadas ao usuário Operador.
        """
        queryset, use_distinct = super().get_search_results(
            request, queryset, search_term
        )

        field_name = request.GET.get("field_name")

        if field_name:
            if (
                field_name == UNIDADE_ADMINISTRATIVA_ORIGEM_AUTOCOMPLETE
                and request.user.is_operador_inventario
            ):
                uas_user = uas_do_usuario(request.user)
                queryset = queryset.filter(
                    id__in=uas_user.values_list("id", flat=True),
                    status=UnidadeAdministrativa.ATIVA,
                )
            else:
                queryset = queryset.filter(status=UnidadeAdministrativa.ATIVA)

        return queryset, use_distinct

    def get_form(self, request, obj=None, **kwargs):

        form = super().get_form(request, obj, **kwargs)

        if obj:  # Só valida na edição
            original_clean = form.clean

            def custom_clean(form_self):
                cleaned_data = original_clean(form_self)

                if cleaned_data.get("status") == UnidadeAdministrativa.INATIVA:
                    original = UnidadeAdministrativa.objects.get(pk=obj.pk)

                    if original.status == UnidadeAdministrativa.ATIVA:

                        if not obj.pode_inativar():
                            raise ValidationError(
                                f"Não é possível inativar a unidade '{obj.nome}' pois existem bens patrimoniais vinculados a ela. "
                                "Transfira ou remova todos os bens antes de inativar."
                            )

                return cleaned_data

            form.clean = custom_clean

        return form

    def save_model(self, request, obj, form, change):

        super().save_model(request, obj, form, change)

        if change and obj.status == UnidadeAdministrativa.INATIVA:
            messages.success(
                request,
                f"Unidade '{obj.nome}' inativada com sucesso. O histórico foi preservado.",
            )
