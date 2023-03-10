from django.contrib import admin
from bem_patrimonial.models import (BemPatrimonial, HistoricoStatusBemPatrimonial, SolicitacaoMovimentacaoBemPatrimonial,
                                    HistoricoMovimentacaoBemPatrimonial, APROVADO, NAO_APROVADO)
from import_export.admin import ImportExportModelAdmin
from rangefilter.filters import DateRangeFilter
from bem_patrimonial.emails import envia_email_cadastro_nao_aprovado


class SolicitacaoMovimentacaoBemPatrimoniallInline(admin.StackedInline):
    model = SolicitacaoMovimentacaoBemPatrimonial
    extra = 0
    readonly_fields = ('solicitado_por', 'aprovado_por', 'rejeitado_por', 'status', )


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
    search_fields = ('nome', 'descricao', 'marca', 'modelo', 'localizacao', )
    search_help_text = 'Pesquise por nome, descrição, marca, modelo ou localização.'

    list_filter = (
        'status',
        ('criado_em', DateRangeFilter),
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

    inlines = [HistoricoStatusBemPatrimonialInline, HistoricoMovimentacaoBemPatrimonialInline, SolicitacaoMovimentacaoBemPatrimoniallInline, ]

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
            return BemPatrimonial.objects.filter(status=APROVADO,
                                                 unidade_administrativa=request.user.unidade_administrativa)
        return BemPatrimonial.objects.filter(status=APROVADO)

    def get_inline_instances(self, request, obj=None):
        inline_instances = []
        inlines = self.inlines
        for inline_class in inlines:
            inline = inline_class(self.model, self.admin_site)
            if (inline_class is SolicitacaoMovimentacaoBemPatrimoniallInline and (not (obj and obj.pode_solicitar_movimentacao))):
                pass
            else:
                inline_instances.append(inline)
        return inline_instances

    def get_formsets(self, request, obj=None):
        for inline in self.get_inline_instances(request, obj):
            yield inline.get_formset(request, obj)

    def save_formset(self, request, form, formset, change):
        if formset.model is HistoricoStatusBemPatrimonial:
            self.save_status(request, form, formset, change)
        if formset.model is SolicitacaoMovimentacaoBemPatrimonial:
            self.save_solicitacao(request, form, formset, change)

        formset.save()

    def save_status(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for instance in instances:
            instance.atualizado_por = request.user
            instance.save()
            self.check_status(instance)

        formset.save_m2m()

    def check_status(self, instance):
        if instance.status is NAO_APROVADO:
            envia_email_cadastro_nao_aprovado(instance)

    def save_solicitacao(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for instance in instances:
            instance.solicitado_por = request.user
            instance.save()
            # TODO envia email nova solicitacao

        formset.save_m2m()
