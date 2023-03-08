import datetime
from datetime import timedelta
from django import forms
from django.contrib import admin

from agendamento_suporte.models import AgendamentoSuporte, ConfigAgendaSuporte, DiaSemana, IntervaloHoras
from agendamento_suporte.emails import envia_email_alerta_novo_agendamento
import nested_admin


class AgendamentoSuporteForm(forms.ModelForm):
    data_agendada = forms.DateField(widget=forms.DateInput(
        attrs={
            'type': 'date',
            'class': 'vDateField',
            'id': 'id_data_agendada',
            'onchange': 'onChangeDate();',
            'min': datetime.datetime.today().strftime('%Y-%m-%d'),
            'max': (datetime.datetime.today() + timedelta(days=6)).strftime('%Y-%m-%d')
        }))

    class Media:
        js = ('js/agendamento_suporte/select_horas.js', )

    def __init__(self, *args, **kwargs):
        super(AgendamentoSuporteForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['data_agendada'] = self.instance.data_agendada.strftime('%Y-%m-%d')
            self.initial['hora_agendada'] = self.instance.hora_agendada.strftime('%H:%M')


class AgendamentoSuporteAdmin(admin.ModelAdmin):
    model = AgendamentoSuporte
    list_display = ('id', 'agendado_por', 'data_agendada', 'hora_agendada', 'observacao', )
    fields = ('data_agendada', 'hora_agendada', 'observacao', )
    form = AgendamentoSuporteForm

    def get_queryset(self, request):
        if request.user.is_operador_inventario:
            return AgendamentoSuporte.objects.filter(agendado_por=request.user)
        return AgendamentoSuporte.objects.all()

    def get_value_of_custom_field(self, request):
        time_str = request.POST.get('select_hora_agendada')
        time_date = datetime.datetime.strptime(time_str, '%H:%M')
        return time_date

    def save_model(self, request, obj, form, change):
        # TODO trabalhar cenário em que usuário tenta agendar uma segunda reunião, sendo que ainda existe uma futura.
        # possibilidades: Pedir permissão para substituir | Bloquear usuário de marcar
        time_date = self.get_value_of_custom_field(request)
        obj.hora_agendada = time_date
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
