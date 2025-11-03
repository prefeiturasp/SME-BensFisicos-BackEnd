from datetime import datetime
import re
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.contenttypes.models import ContentType
from dados_comuns.models import HistoricoGeral
from dados_comuns.context import get_user
from dados_comuns.utils import dict_changes
from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario
from bem_patrimonial.emails import (
    envia_email_nova_solicitacao_movimentacao,
    envia_email_cadastro_nao_aprovado,
)
from bem_patrimonial import constants

NUMERO_PATRIMONIAL_REGEX = r"^\d{3}\.\d{9}-\d$"


class BemPatrimonial(models.Model):
    "Classe que representa um bem patrimonial"

    # obrigatórios
    nome = models.CharField("Nome do bem", max_length=255, null=False, blank=False)
    descricao = models.TextField("Descrição", null=False, blank=False)
    numero_processo = models.CharField(
        "Número do processo de incorporação", max_length=64, null=False, blank=False
    )
    valor_unitario = models.DecimalField(
        "Valor unitário", max_digits=16, decimal_places=2, blank=False, null=False
    )
    marca = models.CharField("Marca", max_length=255, null=False, blank=False)
    modelo = models.CharField("Modelo", max_length=255, null=False, blank=False)

    localizacao = models.CharField("Localização", max_length=255, null=True, blank=True)
    numero_patrimonial = models.CharField(
        "Número Patrimonial",
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        help_text="Formato padrão: 000.000000000-0",
        db_index=True,
    )
    numero_formato_antigo = models.BooleanField(
        "Formato anterior",
        default=False,
        help_text="Se marcado, não valida formato do número (valor livre).",
    )
    sem_numeracao = models.BooleanField(
        "Sem número patrimonial",
        default=False,
        help_text="Se marcado, o sistema atribui automaticamente",
    )
    foto = models.ImageField("Foto", upload_to="bens/", null=True, blank=True)
    status = models.CharField(
        "Status",
        max_length=30,
        choices=constants.STATUS,
        default=constants.AGUARDANDO_APROVACAO,
        null=False,
        blank=False,
    )
    unidade_administrativa = models.ForeignKey(
        UnidadeAdministrativa,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bems_patrimonial",
    )
    criado_por = models.ForeignKey(
        Usuario,
        verbose_name="Criado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    criado_em = models.DateTimeField("Criado em", auto_now=True)
    atualizado_em = models.DateTimeField(
        "Atualizado em", auto_now=True, null=True, blank=True
    )
    AUDIT_TRACK_FIELDS = (
        "numero_patrimonial",
        "numero_formato_antigo",
        "sem_numeracao",
        "nome",
        "descricao",
        "valor_unitario",
        "marca",
        "modelo",
        "numero_processo",
        "numero_cimbpm",
        "localizacao",
        "foto",
        "unidade_administrativa",
        "status",
    )
    AUDIT_IGNORE_FIELDS = ("id", "criado_em", "atualizado_em", "criado_por")

    def __str__(self):
        return f'{self.numero_patrimonial} - {self.nome}' if self.numero_patrimonial else self.nome

    class Meta:
        verbose_name = "bem patrimonial"
        verbose_name_plural = "bens patrimoniais"

    def clean(self):
        if not self.pk and self.numero_formato_antigo and self.sem_numeracao:
            raise ValidationError(
                "Selecione 'Formato antigo' OU 'Sem numeração' — não ambos."
            )

        if not self.sem_numeracao and not (
            self.numero_patrimonial and str(self.numero_patrimonial).strip()
        ):
            raise ValidationError(
                {
                    "numero_patrimonial": "Informe o Número Patrimonial ou marque 'Sem numeração'."
                }
            )

        if (not self.numero_formato_antigo) and (not self.sem_numeracao):
            if not re.fullmatch(
                NUMERO_PATRIMONIAL_REGEX, self.numero_patrimonial or ""
            ):
                raise ValidationError(
                    {"numero_patrimonial": "Número Patrimonial incompleto"}
                )

    def save(self, *args, **kwargs):
        is_create = self._state.adding or (self.pk is None)
        original = None
        if not is_create:
            try:
                original = type(self).objects.get(pk=self.pk)
            except type(self).DoesNotExist:
                original = None

        gerar_auto = bool(self.sem_numeracao and not self.numero_patrimonial)

        super(BemPatrimonial, self).save(*args, **kwargs)

        if gerar_auto and not self.numero_patrimonial:
            base_id = self.pk

            while True:
                id_str = str(base_id).zfill(12)
                numero_formatado = f"000.{id_str}-0"

                if (
                    not type(self)
                    .objects.filter(numero_patrimonial=numero_formatado)
                    .exists()
                ):
                    break
                base_id += 1

            self.numero_patrimonial = numero_formatado
            super(BemPatrimonial, self).save(update_fields=["numero_patrimonial"])
        if not is_create and original:
            # respeita update_fields (se veio)
            only = kwargs.get("update_fields")
            fields = self.AUDIT_TRACK_FIELDS
            changes = dict_changes(
                original,
                self,
                fields=fields,
                only=only,
                ignore=self.AUDIT_IGNORE_FIELDS,
            )
            if changes:
                ct = ContentType.objects.get_for_model(type(self))
                user = get_user()
                HistoricoGeral.objects.bulk_create(
                    [
                        HistoricoGeral(
                            content_type=ct,
                            object_id=str(self.pk),
                            campo=field,
                            valor_antigo=old,
                            valor_novo=new,
                            alterado_por=user,
                        )
                        for field, (old, new) in changes.items()
                    ]
                )

    @property
    def pode_solicitar_movimentacao(self):
        return self.status == constants.APROVADO

    @property
    def tem_movimentacao_pendente(self):
        return self.movimentacaobempatrimonial_set.filter(
            status=constants.ENVIADA
        ).exists()

    def set_unidade_administrative(self, unidade):
        self.unidade_administrativa = unidade
        self.save()


class StatusBemPatrimonial(models.Model):
    "Classe que representa o histórico de mudança de status do bem patrimonial"

    bem_patrimonial = models.ForeignKey(
        BemPatrimonial,
        verbose_name="Bem patrimonial",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    status = models.CharField(
        "Status",
        choices=constants.STATUS,
        max_length=30,
        default=constants.AGUARDANDO_APROVACAO,
        null=False,
        blank=False,
    )
    # opcional
    observacao = models.TextField("Observação", null=True, blank=True)
    # controle
    atualizado_por = models.ForeignKey(
        Usuario,
        verbose_name="Atualizado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    atualizado_em = models.DateTimeField(
        "Atualizado em", auto_now=True, null=True, blank=True
    )

    def save(self, *args, **kwargs):
        self.atualizado_em = datetime.now()
        self.sincroniza_status_bem_patrimonial()
        return super(StatusBemPatrimonial, self).save(*args, **kwargs)

    def __str__(self) -> str:
        return str(self.pk)

    class Meta:
        verbose_name = "status do bem patrimonial"
        verbose_name_plural = "histórico status do bem patrimonial"

    def sincroniza_status_bem_patrimonial(self):
        if self.bem_patrimonial.status is not constants.APROVADO:
            self.bem_patrimonial.status = self.status
            self.bem_patrimonial.save()


class MovimentacaoBemPatrimonial(models.Model):
    "Classe que representa uma solicitacao de movimentacao de um bem patrimonial"

    # obrigatórios
    bem_patrimonial = models.ForeignKey(
        BemPatrimonial,
        verbose_name="Bem patrimonial",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    unidade_administrativa_origem = models.ForeignKey(
        UnidadeAdministrativa,
        related_name="%(class)s_origem",
        verbose_name="Unidade administrativa origem",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    unidade_administrativa_destino = models.ForeignKey(
        UnidadeAdministrativa,
        related_name="%(class)s_destino",
        verbose_name="Unidade administrativa destino",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    status = models.CharField(
        "Status",
        choices=constants.STATUS_MOVIMENTACAO,
        max_length=30,
        default=constants.ENVIADA,
        null=False,
        blank=False,
    )
    observacao = models.TextField("Observacao", null=True, blank=True)
    # controle
    solicitado_por = models.ForeignKey(
        Usuario,
        verbose_name="Solicitado por",
        related_name="%(class)s_solicitadopor",
        on_delete=models.DO_NOTHING,
        null=False,
        blank=False,
    )
    aprovado_por = models.ForeignKey(
        Usuario,
        verbose_name="Aprovado por",
        related_name="%(class)s_aprovadopor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    rejeitado_por = models.ForeignKey(
        Usuario,
        verbose_name="Rejeitado por",
        related_name="%(class)s_rejeitadopor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    cancelado_por = models.ForeignKey(
        Usuario,
        verbose_name="Cancelado por",
        related_name="%(class)s_canceladopor",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    criado_em = models.DateTimeField("Criado em", auto_now=True)
    atualizado_em = models.DateTimeField(
        "Atualizado em", auto_now=True, null=True, blank=True
    )

    def __str__(self) -> str:
        return "Solicitação #{}".format(str(self.pk))

    class Meta:
        verbose_name = "movimentação de bem patrimonial"
        verbose_name_plural = "movimentações de bem patrimonial"

    def save(self, *args, **kwargs):
        if not self.atualizado_em:
            self.atualizado_em = datetime.now()
        return super(MovimentacaoBemPatrimonial, self).save(*args, **kwargs)

    @property
    def aceita(self):
        return self.status == constants.ACEITA

    @property
    def rejeitada(self):
        return self.status == constants.REJEITADA

    @property
    def cancelada(self):
        return self.status == constants.CANCELADA_GESTOR

    def aprovar_solicitacao(self, usuario):
        if self.aceita or self.status != constants.ENVIADA:
            return

        bem = self.bem_patrimonial
        bem.unidade_administrativa = self.unidade_administrativa_destino
        bem.status = constants.APROVADO
        bem.save()

        self.status = constants.ACEITA
        self.aprovado_por = usuario
        self.save()

    def rejeitar_solicitacao(self, usuario):
        if not self.rejeitada and self.status == constants.ENVIADA:
            self.status = constants.REJEITADA
            self.rejeitado_por = usuario
            self.save()

            self.bem_patrimonial.status = constants.APROVADO
            self.bem_patrimonial.save()

    def cancelar_solicitacao(self, usuario):
        if not self.cancelada and self.status == constants.ENVIADA:
            self.status = constants.CANCELADA_GESTOR
            self.cancelado_por = usuario
            self.save()

            self.bem_patrimonial.status = constants.APROVADO
            self.bem_patrimonial.save()


@receiver(post_save, sender=BemPatrimonial)
def cria_primeiro_status_bem_patrimonial(sender, instance, created, **kwargs):
    if created and instance.status is constants.AGUARDANDO_APROVACAO:
        instance.statusbempatrimonial_set.create(
            status=constants.AGUARDANDO_APROVACAO, atualizado_por=instance.criado_por
        )


@receiver(post_save, sender=StatusBemPatrimonial)
def envia_email_status_reprovado(sender, instance, created, **kwargs):
    if created and (instance.status == constants.NAO_APROVADO):
        envia_email_cadastro_nao_aprovado(instance)


@receiver(post_save, sender=MovimentacaoBemPatrimonial)
def bloquear_bem_em_movimentacao(sender, instance, created, **kwargs):
    if created:
        bem = instance.bem_patrimonial
        bem.status = constants.BLOQUEADO
        bem.save()

        StatusBemPatrimonial.objects.create(
            bem_patrimonial=bem,
            status=constants.BLOQUEADO,
            atualizado_por=instance.solicitado_por,
            observacao=f"Bem bloqueado para movimentação #{instance.pk}",
        )


@receiver(post_save, sender=MovimentacaoBemPatrimonial)
def envia_email_alert_nova_solicitacao(sender, instance, created, **kwargs):
    if created:
        emails = []
        usuarios = Usuario.objects.filter(
            is_active=True,
            unidade_administrativa=instance.unidade_administrativa_destino,
        ).only("email")
        for usuario in usuarios:
            if usuario.email:
                emails.append(usuario.email)

        envia_email_nova_solicitacao_movimentacao(instance, emails)
