from django.contrib import admin
from bem_patrimonial.models import BemPatrimonial, SolicitacaoMovimentacaoBemPatrimonial
from .admins.bem_patrimonial import BemPatrimonialAdmin
from .admins.solicitacao_movimentacao import SolicitacaoMovimentacaoBemPatrimonialAdmin

admin.site.register(BemPatrimonial, BemPatrimonialAdmin)
admin.site.register(SolicitacaoMovimentacaoBemPatrimonial, SolicitacaoMovimentacaoBemPatrimonialAdmin)
