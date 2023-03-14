from django.contrib import admin
from django.contrib import messages
from django.forms import ValidationError
from bem_patrimonial.admins.forms.form_solicitacao_movimentacao import SolicitacaoMovimentacaoBemPatrimonialForm
from bem_patrimonial.models import SolicitacaoMovimentacaoBemPatrimonial
from bem_patrimonial.emails import envia_email_solicitacao_movimentacao_aceita, envia_email_solicitacao_movimentacao_rejeitada


def aprovar_solicitacao(modeladmin, request, queryset):
    for item in queryset:
        if item.solicitado_por.pk == request.user.pk:
            messages.add_message(request, messages.WARNING, 'Não é possível realizar essa ação.')
            return
        if item.aceita:
            messages.add_message(request, messages.WARNING, 'Solicitação já foi aprovada.')
            return

        item.aprovar_solicitacao_e_atualizar_historico(request.user)
        messages.add_message(request, messages.INFO, 'Movimentação aprovada com sucesso')
        envia_email_solicitacao_movimentacao_aceita(item.bem_patrimonial, item.solicitado_por.email)


def rejeitar_solicitacao(modeladmin, request, queryset):
    for item in queryset:
        if item.solicitado_por.pk == request.user.pk:
            messages.add_message(request, messages.WARNING, 'Não é possível realizar essa ação.')
            return
        if item.rejeitada:
            messages.add_message(request, messages.WARNING, 'Solicitação já foi rejeitada.')
            return

        item.rejeitar_solicitacao(request.user)
        messages.add_message(request, messages.INFO, 'Movimentação rejeitada com sucesso')
        envia_email_solicitacao_movimentacao_rejeitada(item.bem_patrimonial, item.solicitado_por.email)


class SolicitacaoMovimentacaoBemPatrimonialAdmin(admin.ModelAdmin):
    model = SolicitacaoMovimentacaoBemPatrimonial
    list_display = ('id', 'bem_patrimonial', 'solicitado_por', 'status', 'criado_em', 'atualizado_em', )
    autocomplete_fields = ("bem_patrimonial",)
    readonly_fields = (
        'solicitado_por',
        'aprovado_por',
        'rejeitado_por',
        'status',
    )
    list_filter = (
        'status',
    )
    actions = [
        aprovar_solicitacao,
        rejeitar_solicitacao
    ]

    form = SolicitacaoMovimentacaoBemPatrimonialForm

    def get_form(self, request, *args, **kwargs):
        form = super(SolicitacaoMovimentacaoBemPatrimonialAdmin, self).get_form(request, *args, **kwargs)
        form.request = request
        return form

    def get_queryset(self, request):
        if request.user.is_operador_inventario:
            return SolicitacaoMovimentacaoBemPatrimonial.objects.filter(
                unidade_administrativa_destino=request.user.unidade_administrativa
            )
        return SolicitacaoMovimentacaoBemPatrimonial.objects.all()

    def save_model(self, request, obj, form, change):
        if obj.id is None:
            obj.solicitado_por = request.user
            super().save_model(request, obj, form, change)
        else:
            super().save_model(request, obj, form, change)
