from django.contrib import admin
from bem_patrimonial.models import BemPatrimonial, MovimentacaoBemPatrimonial
from .admins.bem_patrimonial import BemPatrimonialAdmin
from .admins.movimentacao_bem_patrimonial import MovimentacaoBemPatrimonialAdmin

admin.site.register(BemPatrimonial, BemPatrimonialAdmin)
admin.site.register(MovimentacaoBemPatrimonial, MovimentacaoBemPatrimonialAdmin)
