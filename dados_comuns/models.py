from datetime import datetime
from django.db import models


class UnidadeAdministrativa(models.Model):
    '''Classe que representa uma unidade administrativa'''
    codigo = models.CharField("Codigo", max_length=255, null=False, blank=False)
    sigla = models.CharField("sigla", max_length=255, null=False, blank=False)
    nome = models.CharField("nome", max_length=255, null=False, blank=False)
    # controle
    created_at = models.DateTimeField("Criado em", auto_now=True)
    updated_at = models.DateTimeField("Atualizado em", auto_now=True, null=True, blank=True)

    def __str__(self):
        return '{} - {}'.format(self.codigo, self.sigla)

    class Meta:
        verbose_name = 'unidade administrativa'
        verbose_name_plural = 'unidades administrativas'
        ordering = ['codigo', 'nome', 'sigla']

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super(UnidadeAdministrativa, self).save(*args, **kwargs)
