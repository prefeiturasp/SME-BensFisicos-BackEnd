from datetime import datetime
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
from django.conf import settings


class UnidadeAdministrativa(models.Model):
    """Classe que representa uma unidade administrativa"""

    ATIVA = "ativa"
    INATIVA = "inativa"

    STATUS_CHOICES = (
        (ATIVA, "Ativa"),
        (INATIVA, "Inativa"),
    )

    codigo = models.CharField("Codigo", max_length=255, null=False, blank=False)
    sigla = models.CharField("sigla", max_length=255, null=False, blank=False)
    nome = models.CharField("nome", max_length=255, null=False, blank=False)
    status = models.CharField(
        "Status",
        max_length=10,
        choices=STATUS_CHOICES,
        default=ATIVA,
        null=False,
        blank=False,
    )
    # controle
    created_at = models.DateTimeField("Criado em", auto_now=True)
    updated_at = models.DateTimeField(
        "Atualizado em", auto_now=True, null=True, blank=True
    )

    def __str__(self):
        return "{} - {}".format(self.codigo, self.sigla)

    class Meta:
        verbose_name = "unidade administrativa"
        verbose_name_plural = "unidades administrativas"
        ordering = ["codigo", "sigla", "nome"]

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super(UnidadeAdministrativa, self).save(*args, **kwargs)

    @property
    def is_ativa(self):
        return self.status == self.ATIVA

    def pode_inativar(self):
        return not self.bems_patrimonial.exists()


class HistoricoGeral(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=64, db_index=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    campo = models.CharField("Campo alterado", max_length=128)
    valor_antigo = models.TextField("Valor antigo", null=True, blank=True)
    valor_novo = models.TextField("Valor novo", null=True, blank=True)

    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Alterado por"
    )
    alterado_em = models.DateTimeField("Alterado em", default=timezone.now, db_index=True)

    class Meta:
        verbose_name = "histórico geral"
        verbose_name_plural = "histórico geral"
        ordering = ("-alterado_em", "content_type", "object_id")
        indexes = [models.Index(fields=["content_type", "object_id", "alterado_em"])]

    def __str__(self):
        return f"{self.content_type}.{self.object_id} | {self.campo}"
