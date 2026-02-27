from django.contrib import admin
from bem_patrimonial.admins.baixa_fisica_bem_patrimonial import (
    BaixaFisicaBemPatrimonialAdmin,
)
from bem_patrimonial.models import (
    BemPatrimonial,
    MovimentacaoBemPatrimonial,
    BaixaFisicaBemPatrimonial,
)
from .admins.bem_patrimonial import BemPatrimonialAdmin
from .admins.movimentacao_bem_patrimonial import MovimentacaoBemPatrimonialAdmin

admin.site.register(BemPatrimonial, BemPatrimonialAdmin)
admin.site.register(MovimentacaoBemPatrimonial, MovimentacaoBemPatrimonialAdmin)
admin.site.register(BaixaFisicaBemPatrimonial, BaixaFisicaBemPatrimonialAdmin)
