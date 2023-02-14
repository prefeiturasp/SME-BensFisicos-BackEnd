from django.contrib import admin
from django import forms
from bem_patrimonial.models import BemPatrimonial
from import_export.admin import ImportExportModelAdmin
from rangefilter.filters import DateRangeFilter


class BemPatrimonialAdmin(ImportExportModelAdmin):
    model = BemPatrimonial
    list_display = ('id', 'descricao', 'criado_em', )
    search_fields = ('nome', 'descricao', 'marca', 'modelo', 'localizacao', )
    search_help_text = 'Pesquise por nome, descrição, marca, modelo ou localização.'

    list_filter = (
        ('criado_em', DateRangeFilter),
    )
    fields = (
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


admin.site.register(BemPatrimonial, BemPatrimonialAdmin)
