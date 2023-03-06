from django import forms
from django.contrib import admin
from django.contrib.admin.widgets import AdminDateWidget

from agendamento_suporte.models import AgendamentoSuporte, ConfigAgendaSuporte, DiaSemana, IntervaloHoras
from agendamento_suporte.emails import envia_email_alerta_novo_agendamento
import nested_admin


class AgendamentoSuporteForm(forms.ModelForm):
    horarios = forms.Select()


class AgendamentoSuporteAdmin(admin.ModelAdmin):
    model = AgendamentoSuporte
    list_display = ('id', 'agendado_por', 'data_agendada', 'hora_agendada', 'observacao', )
    fields = ('data_agendada', 'horarios', 'observacao', )
    form = AgendamentoSuporteForm

    def get_fieldsets(self, request, obj=None):
        fieldsets = super(AgendamentoSuporteAdmin, self).get_fieldsets(request, obj)
        fieldsets[0][1]['fields'] += ('horarios', )
        return fieldsets

    def get_queryset(self, request):
        if request.user.is_operador_inventario:
            return AgendamentoSuporte.objects.filter(agendado_por=request.user)
        return AgendamentoSuporte.objects.all()

    def save_model(self, request, obj, form, change):
        if obj.id is None:
            obj.agendado_por = request.user
            envia_email_alerta_novo_agendamento()
            super().save_model(request, obj, form, change)
        else:
            super().save_model(request, obj, form, change)


class IntervaloHorasInline(nested_admin.NestedStackedInline):
    model = IntervaloHoras
    extra = 0
    fields = (('hora_inicio', 'hora_fim'), )

    class Media:
        css = {
            'all': ('css/custom_admin.css', )
        }


class DiaSemanaInline(nested_admin.NestedStackedInline):
    model = DiaSemana
    extra = 0
    inlines = [IntervaloHorasInline,]
    readonly_fields = ('dia_semana', )
    sortable_options = {
        'disabled': True,
    }


class ConfigAgendaSuporteAdmin(nested_admin.NestedModelAdmin):
    model = ConfigAgendaSuporte
    inlines = [DiaSemanaInline,]


admin.site.register(ConfigAgendaSuporte, ConfigAgendaSuporteAdmin)
admin.site.register(AgendamentoSuporte, AgendamentoSuporteAdmin)
