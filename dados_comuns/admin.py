from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from import_export.admin import ImportExportModelAdmin
from import_export.formats.base_formats import CSV, XLS, XLSX
from dados_comuns.escopo import (
    filtrar_ua_destino_por_uo_do_usuario,
    filtrar_ua_origem_por_escopo,
)
from dados_comuns.forms.unidade_administrativa_admin_form import (
    UnidadeAdministrativaAdminForm,
)
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria
from dados_comuns.resources import UnidadeAdministrativaResource
from dados_comuns.formats import UnidadeAdministrativaPDFFormat


UNIDADE_ADMINISTRATIVA_ORIGEM_AUTOCOMPLETE = "unidade_administrativa_origem"
UNIDADE_ADMINISTRATIVA_DESTINO_AUTOCOMPLETE = "unidade_administrativa_destino"


class StatusFilter(admin.SimpleListFilter):
    title = "Status"
    parameter_name = "status"

    def lookups(self, request, model_admin):
        return UnidadeAdministrativa.STATUS_CHOICES

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(status=self.value())
        return queryset


class AtivaFilter(admin.SimpleListFilter):
    title = "Ativa"
    parameter_name = "ativa"

    def lookups(self, request, model_admin):
        return (
            ("1", "Ativa"),
            ("0", "Inativa"),
        )

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset.filter(ativa=True)
        if self.value() == "0":
            return queryset.filter(ativa=False)
        return queryset


@admin.register(UnidadeOrcamentaria)
class UnidadeOrcamentariaAdmin(ImportExportModelAdmin):
    """
    Cadastro de Unidades Orçamentárias (UO).

    Regra de acesso:
    - Apenas superuser pode criar/editar/visualizar (UO é o nível mais alto do sistema).
    """

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):

        return False

    def has_import_permission(self, request):
        return False

    def has_export_permission(self, request):
        return request.user.is_superuser

    list_display = (
        "codigo",
        "nome",
        "ativa",
    )
    search_fields = (
        "codigo",
        "nome",
    )
    search_help_text = "Pesquise por código ou nome."
    ordering = ("codigo", "nome")

    list_filter = (AtivaFilter,)

    fields = ("codigo", "nome", "ativa", "sigla")

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        original_clean = form.clean

        def custom_clean(form_self):
            cleaned_data = original_clean(form_self)
            codigo = (cleaned_data.get("codigo") or "").strip()
            nome = (cleaned_data.get("nome") or "").strip()

            if not codigo:
                raise ValidationError({"codigo": "Código é obrigatório."})
            if not nome:
                raise ValidationError({"nome": "Nome é obrigatório."})

            cleaned_data["codigo"] = codigo
            cleaned_data["nome"] = nome

            return cleaned_data

        form.clean = custom_clean
        return form

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        if change:
            messages.success(request, "Unidade Orçamentária atualizada com sucesso.")
        else:
            messages.success(request, "Unidade Orçamentária criada com sucesso.")

    def get_export_formats(self):
        return [CSV, XLSX, XLS]


@admin.register(UnidadeAdministrativa)
class UnidadeAdministrativaAdmin(ImportExportModelAdmin):
    resource_class = UnidadeAdministrativaResource
    form = UnidadeAdministrativaAdminForm

    def has_import_permission(self, request):
        return False

    def has_export_permission(self, request):
        return request.user.is_gestor_patrimonio

    list_display = (
        "codigo",
        "sigla",
        "nome",
        "unidade_orcamentaria",
        "status",
    )

    search_fields = (
        "sigla",
        "nome",
        "codigo",
        "unidade_orcamentaria__codigo",
        "unidade_orcamentaria__nome",
    )

    search_help_text = "Pesquise por sigla, nome, código ou Unidade Orçamentária."
    ordering = ("unidade_orcamentaria__codigo", "codigo", "sigla", "nome")

    list_filter = [
        StatusFilter,
        ("unidade_orcamentaria", admin.RelatedOnlyFieldListFilter),
    ]

    fields = [
        "unidade_orcamentaria",
        "codigo_sufixo",
        "sigla",
        "nome",
        "status",
    ]

    class Media:
        js = ("admin/ua_codigo_prefixo.js",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.user.is_superuser:
            return qs

        uo = getattr(request.user, "unidade_orcamentaria", None)
        if uo:
            return qs.filter(unidade_orcamentaria=uo)

        ua = getattr(request.user, "unidade_administrativa", None)
        if ua:
            return qs.filter(pk=ua.pk)

        return qs.none()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "unidade_orcamentaria":

            if not request.user.is_superuser:
                if request.user.unidade_orcamentaria_id:
                    kwargs["queryset"] = UnidadeOrcamentaria.objects.filter(
                        pk=request.user.unidade_orcamentaria_id
                    )
                else:
                    kwargs["queryset"] = UnidadeOrcamentaria.objects.none()
            else:
                kwargs["queryset"] = UnidadeOrcamentaria.objects.all()

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        if "unidade_orcamentaria" in form.base_fields:
            form.base_fields["unidade_orcamentaria"].required = True

        if (
            obj is None
            and request.user.unidade_orcamentaria_id
            and "unidade_orcamentaria" in form.base_fields
        ):
            form.base_fields["unidade_orcamentaria"].initial = (
                request.user.unidade_orcamentaria_id
            )

        if not request.user.is_superuser and "unidade_orcamentaria" in form.base_fields:
            form.base_fields["unidade_orcamentaria"].disabled = True

        original_clean = form.clean

        def custom_clean(form_self):
            cleaned_data = original_clean(form_self)
            uo = cleaned_data.get("unidade_orcamentaria")

            if not uo:
                raise ValidationError(
                    {"unidade_orcamentaria": "Unidade Orçamentária é obrigatória."}
                )

            if not request.user.is_superuser:
                if uo != request.user.unidade_orcamentaria:
                    raise ValidationError(
                        {
                            "unidade_orcamentaria": "Você não pode cadastrar Unidade Administrativa em outra Unidade Orçamentária."
                        }
                    )

            return cleaned_data

        form.clean = custom_clean
        return form

    def get_search_results(self, request, queryset, search_term):
        queryset, use_distinct = super().get_search_results(
            request, queryset, search_term
        )

        field_name = request.GET.get("field_name")

        # aplica regras só para autocomplete (quando field_name existe)
        if field_name in (
            UNIDADE_ADMINISTRATIVA_ORIGEM_AUTOCOMPLETE,
            UNIDADE_ADMINISTRATIVA_DESTINO_AUTOCOMPLETE,
        ):
            if field_name == UNIDADE_ADMINISTRATIVA_ORIGEM_AUTOCOMPLETE:
                queryset = filtrar_ua_origem_por_escopo(request.user, queryset)

            elif field_name == UNIDADE_ADMINISTRATIVA_DESTINO_AUTOCOMPLETE:
                queryset = filtrar_ua_destino_por_uo_do_usuario(request.user, queryset)

            # sempre só ativas no autocomplete
            queryset = queryset.filter(status=UnidadeAdministrativa.ATIVA)

        return queryset, use_distinct

    def save_model(self, request, obj, form, change):
        obj.codigo = form.cleaned_data["codigo"]

        super().save_model(request, obj, form, change)

        if change and obj.status == UnidadeAdministrativa.INATIVA:
            messages.success(
                request,
                f"Unidade '{obj.nome}' inativada com sucesso. O histórico foi preservado.",
            )

    def get_export_formats(self):
        return [CSV, XLSX, XLS, UnidadeAdministrativaPDFFormat]

    def get_export_data(self, file_format, queryset, *args, **kwargs):
        if isinstance(file_format, UnidadeAdministrativaPDFFormat):
            request = kwargs.get("request")
            file_format._export_request = request
            file_format._export_queryset = queryset
        return super().get_export_data(file_format, queryset, *args, **kwargs)
