from datetime import datetime
from django.db import models
from django.forms import ValidationError

from .constants import DAY_WEEK_CHOICES


class ConfigAgendaSuporte(models.Model):
    '''Classe que representa a agenda semanal do setor de Bem Patrimonial'''
    nome = models.CharField("Nome", max_length=255, null=False, blank=False)

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super(ConfigAgendaSuporte, self).save(*args, **kwargs)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'configuração de agenda'
        verbose_name_plural = 'configuração de agenda'

    def clean(self):
        if ConfigAgendaSuporte.objects.exists() and not self.pk:
            raise ValidationError("Somente 1 configuração de agenda é permitida.")


class DiaSemana(models.Model):
    '''Classe que representa o dia da semana para configuração de agenda'''
    agenda = models.ForeignKey(ConfigAgendaSuporte, verbose_name="Agenda", on_delete=models.SET_NULL, null=True, blank=True)
    dia_semana = models.PositiveIntegerField("Dia da semana", choices=DAY_WEEK_CHOICES, null=False)

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super(DiaSemana, self).save(*args, **kwargs)

    def __str__(self):
        return self.get_day_week_display()

    def get_day_week_display(self):
        for code, label in DAY_WEEK_CHOICES:
            if self.dia_semana == code:
                break
        return label

    class Meta:
        verbose_name = 'dia da semana'
        verbose_name_plural = 'dias da semana'
        unique_together = ('dia_semana', 'agenda',)


class IntervaloHoras(models.Model):
    '''Classe que representa os intervalos de horário de cada dia da semana'''
    agenda = models.ForeignKey(DiaSemana, verbose_name="Agenda suporte", on_delete=models.CASCADE,
                               null=False, blank=False)
    hora_inicio = models.TimeField(verbose_name="Hora início", null=False, blank=False)
    hora_fim = models.TimeField(verbose_name="Hora fim", null=False, blank=False)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True, null=True, blank=True)

    def __str__(self):
        return '{} - {}' .format(self.hora_inicio, self.hora_fim)

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super(IntervaloHoras, self).save(*args, **kwargs)

    class Meta:
        verbose_name = 'intervalo de horas'
        verbose_name_plural = 'intervalos de horas'


class AgendamentoSuporte(models.Model):
    '''Classe que representa um registro de agendamento para suporte de cadastro de Bem Patrimonial'''
    agendado_por = models.ForeignKey("usuario.Usuario", verbose_name="Agendado por", on_delete=models.DO_NOTHING,
                                     null=False, blank=False)
    data_agendada = models.DateField("Data", null=False, blank=False)
    hora_agendada = models.TimeField("Hora", null=False, blank=False)
    # opcional
    observacao = models.TextField("Observacao", null=True, blank=True)
    # controle
    created_at = models.DateTimeField("Criado em", auto_now=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True, null=True, blank=True)

    def __str__(self):
        return '{}  {} - {}'.format(self.agendado_por.nome, self.data_agendada.strftime('%d/%m/%y'), self.hora_agendada.strftime('%H:%M'))

    class Meta:
        verbose_name = 'agendamento de suporte'
        verbose_name_plural = 'agendamentos de suporte'

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super(AgendamentoSuporte, self).save(*args, **kwargs)
