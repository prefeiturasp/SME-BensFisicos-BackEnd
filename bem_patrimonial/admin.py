from django.contrib import admin
from django import forms
from bem_patrimonial.models import BemPatrimonial, HistoricoStatusBemPatrimonial, APROVADO, NAO_APROVADO
from import_export.admin import ImportExportModelAdmin
from rangefilter.filters import DateRangeFilter
from bem_patrimonial.emails import envia_email_cadastro_nao_aprovado


class HistoricoStatusBemPatrimonialInline(admin.TabularInline):
    model = HistoricoStatusBemPatrimonial
    extra = 0
    readonly_fields = ('atualizado_por', 'atualizado_em', )


class BemPatrimonialAdmin(ImportExportModelAdmin):
    model = BemPatrimonial
    list_display = ('id', 'status', 'descricao', 'criado_por', 'criado_em', )
    search_fields = ('nome', 'descricao', 'marca', 'modelo', 'localizacao', )
    search_help_text = 'Pesquise por nome, descrição, marca, modelo ou localização.'

    list_filter = (
        'status',
        ('criado_em', DateRangeFilter),
    )

    readonly_fields = ('status', 'criado_por', 'criado_em', 'unidade_administrativa',)

    fields = (
        'status',
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

    inlines = [HistoricoStatusBemPatrimonialInline,]

    def save_model(self, request, obj, form, change):
        if obj.id is None:
            obj.criado_por = request.user
            super().save_model(request, obj, form, change)
        else:
            super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        if request.user.is_operador_inventario:
            return BemPatrimonial.objects.filter(unidade_administrativa=request.user.unidade_administrativa)
        return BemPatrimonial.objects.all()

    def get_export_queryset(self, request):
        if request.user.is_operador_inventario:
            return BemPatrimonial.objects.filter(status=APROVADO, unidade_administrativa=request.user.unidade_administrativa)
        return BemPatrimonial.objects.filter(status=APROVADO)

    def check_status(self, instance):
        if instance.status is NAO_APROVADO:
            envia_email_cadastro_nao_aprovado(instance)

    def save_formset(self, request, form, formset, change):
        # print(formset.model)
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for instance in instances:
            instance.atualizado_por = request.user
            instance.save()
            self.check_status(instance)

        formset.save_m2m()


admin.site.register(BemPatrimonial, BemPatrimonialAdmin)
