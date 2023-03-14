from django.contrib import admin
from django_admin_listfilter_dropdown.filters import DropdownFilter
from bem_patrimonial.models import (BemPatrimonial, HistoricoStatusBemPatrimonial,
                                    HistoricoMovimentacaoBemPatrimonial, APROVADO)
from import_export.admin import ImportExportModelAdmin
from rangefilter.filters import DateRangeFilter


class HistoricoMovimentacaoBemPatrimonialInline(admin.TabularInline):
    model = HistoricoMovimentacaoBemPatrimonial
    extra = 0
    readonly_fields = ('unidade_administrativa', 'solicitacao_movimentacao', 'atualizado_em', )


class HistoricoStatusBemPatrimonialInline(admin.TabularInline):
    model = HistoricoStatusBemPatrimonial
    extra = 0
    readonly_fields = ('atualizado_por', 'atualizado_em', )


class BemPatrimonialAdmin(ImportExportModelAdmin):
    model = BemPatrimonial
    list_display = ('id', 'status', 'descricao', 'criado_por', 'criado_em', )
    search_fields = ('nome', 'descricao', 'marca', 'modelo', 'localizacao', 'numero_processo', )
    search_help_text = 'Pesquise por nome, descrição, marca, modelo, localização ou número de processo.'

    list_filter = (
        'status',
        ('criado_em', DateRangeFilter),
        ('numero_processo', DropdownFilter),
    )

    readonly_fields = ('status', 'criado_por', 'criado_em', 'unidade_administrativa',)

    fields = (
        'status',
        'unidade_administrativa',
        'nome',
        'descricao',
        ('quantidade', 'valor_unitario'),
        ('marca', 'modelo'),
        ('data_compra_entrega'),
        ('origem', 'numero_processo'),
        'autorizacao_no_doc_em',
        ('numero_nibpm', 'numero_cimbpm', 'numero_patrimonial'),
        'localizacao',
        'numero_serie',
    )

    inlines = [HistoricoStatusBemPatrimonialInline, HistoricoMovimentacaoBemPatrimonialInline]

    def save_model(self, request, obj, form, change):
        if obj.id is None:
            obj.criado_por = request.user
            super().save_model(request, obj, form, change)
        else:
            super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        queryset = BemPatrimonial.objects.all()
        if request.user.is_operador_inventario:
            return queryset.filter(unidade_administrativa=request.user.unidade_administrativa)
        return queryset

    def get_export_queryset(self, request):
        queryset = BemPatrimonial.objects.filter(status=APROVADO)
        if request.user.is_operador_inventario:
            return queryset.filter(unidade_administrativa=request.user.unidade_administrativa)
        return queryset

    def save_formset(self, request, form, formset, change):
        if formset.model is HistoricoStatusBemPatrimonial:
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
