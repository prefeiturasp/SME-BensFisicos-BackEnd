from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, OuterRef, Subquery
from bem_patrimonial.models import (
    BemPatrimonial,
    StatusBemPatrimonial,
    UnidadeAdministrativaBemPatrimonial,
)
from bem_patrimonial.formats import PDFFormat
from import_export.admin import ImportExportModelAdmin
from import_export import resources, fields
from rangefilter.filters import DateRangeFilter
from import_export.formats.base_formats import CSV, XLS, XLSX, HTML


class UnidadeAdministrativaBemPatrimonialInline(admin.TabularInline):
    model = UnidadeAdministrativaBemPatrimonial
    extra = 0


class StatusBemPatrimonialInline(admin.TabularInline):
    model = StatusBemPatrimonial
    extra = 0
    readonly_fields = (
        "atualizado_por",
        "atualizado_em",
    )


class BemPatrimonialResource(resources.ModelResource):
    quantidade_unidade = fields.Field(
        column_name="quantidade",
        attribute="quantidade_unidade",
    )

    class Meta:
        model = BemPatrimonial
        fields = (
            "id",
            "status",
            "nome",
            "data_compra_entrega",
            "origem",
            "marca",
            "modelo",
            "descricao",
            "quantidade_unidade",
            "valor_unitario",
            "numero_processo",
            "autorizacao_no_doc_em",
            "numero_nibpm",
            "numero_cimbpm",
            "numero_patrimonial",
            "localizacao",
            "numero_serie",
            "criado_por__nome",
            "criado_em",
        )
        export_order = fields


class BemPatrimonialAdmin(ImportExportModelAdmin):
    model = BemPatrimonial
    list_display = (
        "id",
        "status",
        "descricao",
        "criado_por",
        "criado_em",
    )
    search_fields = (
        "nome",
        "descricao",
        "marca",
        "modelo",
        "localizacao",
        "numero_processo",
    )
    search_help_text = "Pesquise por nome, descrição, marca, modelo, localização ou número de processo."
    resource_class = BemPatrimonialResource

    list_filter = ("status", ("criado_em", DateRangeFilter))

    readonly_fields = (
        "status",
        "criado_por",
        "criado_em",
    )

    fields = (
        "status",
        "nome",
        "descricao",
        ("quantidade", "valor_unitario"),
        ("marca", "modelo"),
        ("data_compra_entrega"),
        ("origem", "numero_processo"),
        "autorizacao_no_doc_em",
        ("numero_nibpm", "numero_cimbpm", "numero_patrimonial"),
        "localizacao",
        "numero_serie",
    )

    inlines = [StatusBemPatrimonialInline, UnidadeAdministrativaBemPatrimonialInline]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        if obj is None:  # Só valida na criação
            original_clean = form.clean

            def custom_clean(form_self):
                cleaned_data = original_clean(form_self)

                if (
                    request.user.unidade_administrativa
                    and not request.user.unidade_administrativa.is_ativa
                ):
                    raise ValidationError(
                        f"Não é possível criar bens patrimoniais. Sua unidade administrativa "
                        f"'{request.user.unidade_administrativa.nome}' está inativa. "
                        "Entre em contato com o gestor de patrimônio."
                    )

                return cleaned_data

            form.clean = custom_clean

        return form

    def save_model(self, request, obj, form, change):
        if obj.id is None:
            obj.criado_por = request.user
            super().save_model(request, obj, form, change)
        else:
            super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        queryset = BemPatrimonial.objects.all()
        if request.user.is_operador_inventario:
            return queryset.filter(
                Q(unidadeadministrativabempatrimonial__quantidade__gt=0)
                & Q(
                    unidadeadministrativabempatrimonial__unidade_administrativa=request.user.unidade_administrativa
                )
            ).distinct("id")
        return queryset

    def get_export_queryset(self, request):
        queryset = super().get_export_queryset(request)

        if request.user.is_operador_inventario:
            queryset = (
                queryset.filter(
                    Q(unidadeadministrativabempatrimonial__quantidade__gt=0)
                    & Q(
                        unidadeadministrativabempatrimonial__unidade_administrativa=request.user.unidade_administrativa
                    )
                )
                .distinct("id")
                .annotate(
                    quantidade_unidade=Subquery(
                        UnidadeAdministrativaBemPatrimonial.objects.filter(
                            bem_patrimonial=OuterRef("id"),
                            unidade_administrativa=request.user.unidade_administrativa,
                        ).values("quantidade")[:1],
                        output_field=models.IntegerField(),
                    )
                )
            )

        return queryset

    def get_export_formats(self):
        return [CSV, XLSX, XLS, HTML, PDFFormat]

    def get_resource_kwargs(self, request, **kwargs):
        rk = super().get_resource_kwargs(request, **kwargs)
        rk["request"] = request
        return rk

    def get_export_data(self, file_format, queryset, *args, **kwargs):
        if isinstance(file_format, PDFFormat):
            request = kwargs.get("request")
            file_format._export_request = request
            file_format._export_queryset = queryset

        return super().get_export_data(file_format, queryset, *args, **kwargs)

    def save_formset(self, request, form, formset, change):
        if formset.model is StatusBemPatrimonial:
            self.save_status(request, form, formset, change)
        formset.save()

    def save_status(self, request, form, formset, change):
        instances = formset.save(commit=False)

        for obj in formset.deleted_objects:
            obj.delete()

        for instance in instances:
            instance.atualizado_por = request.user
            instance.save()

        formset.save_m2m()
