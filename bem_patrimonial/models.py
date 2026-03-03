from datetime import datetime
import re
from django.db.models import Q
from django.dispatch import receiver
from django.db.models.signals import post_save, pre_save
from django.core.exceptions import ValidationError
from django.db import models
from django.db import transaction
from django.utils import timezone
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


NPAT_NUM_REGEX = r"^\d{3}\.\d{9}-\d$"
NPAT_AUTO_REGEX = r"^SEM-NUMERO-\d+$"

VERBOSE_ATUALIZADO_EM = "Atualizado em"


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        return super().update(excluido=True)

    def hard_delete(self):
        return super().delete()

    def alive(self):
        return self.filter(excluido=False)

    def dead(self):
        return self.filter(excluido=True)


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(excluido=False)

    def hard_delete(self):
        return self.get_queryset().hard_delete()


class AllObjectsManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    excluido = models.BooleanField(default=False)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    def delete(self, using=None, keep_parents=False):
        if self.excluido:
            return

        with transaction.atomic():
            self.excluido = True
            self.save(update_fields=["excluido"])

            hook = getattr(self, "_on_soft_delete", None)
            if callable(hook):
                hook()

    class Meta:
        abstract = True


class BaseModel(SoftDeleteModel):
    class Meta:
        abstract = True


class BemPatrimonial(BaseModel):
    "Classe que representa um bem patrimonial"

    # obrigatórios
    nome = models.CharField("Nome do bem", max_length=255, null=False, blank=False)
    descricao = models.TextField("Descrição", null=False, blank=False)
    observacao = models.TextField("Observação", blank=True, default="")
    numero_processo = models.CharField(
        "Número do processo de incorporação",
        max_length=64,
        blank=True,
        default="",
    )
    valor_unitario = models.DecimalField(
        "Valor unitário", max_digits=16, decimal_places=2, blank=False, null=False
    )
    marca = models.CharField("Marca", max_length=255, null=False, blank=False)
    modelo = models.CharField("Modelo", max_length=255, null=False, blank=False)

    localizacao = models.CharField(
        "Localização", max_length=255, blank=True, default=""
    )
    numero_patrimonial = models.CharField(
        "Número Patrimonial",
        max_length=20,
        blank=True,
        default="",
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
        max_length=50,
        choices=constants.STATUS,
        default=constants.AGUARDANDO_APROVACAO,
        null=False,
        blank=False,
    )
    bloqueado_conciliacao = models.BooleanField(
        "Bloqueado por inventário",
        default=False,
        help_text="Se True, bem não pode ser movimentado até atualização de situação na consiliaçãp",
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
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField(
        VERBOSE_ATUALIZADO_EM, auto_now=True, blank=True
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
        "bloqueado_conciliacao",
        "observacao"
    )
    AUDIT_IGNORE_FIELDS = ("id", "criado_em", "atualizado_em", "criado_por")

    def __str__(self):
        return (
            f"{self.numero_patrimonial} - {self.nome}"
            if self.numero_patrimonial
            else self.nome
        )

    class Meta:
        verbose_name = "bem patrimonial"
        verbose_name_plural = "bens patrimoniais"
        constraints = [
            models.UniqueConstraint(
                fields=["numero_patrimonial"],
                condition=Q(excluido=False) & ~Q(numero_patrimonial=""),
                name="uniq_numero_patrimonial_ativo",
            )
        ]

    def _clean_valida_formato_antigo_ou_sem_numeracao(self):
        if not self.pk and self.numero_formato_antigo and self.sem_numeracao:
            raise ValidationError(
                "Selecione 'Formato antigo' OU 'Sem numeração' — não ambos."
            )

    def _clean_valida_numero_obrigatorio(self):
        if not self.sem_numeracao and not (
            self.numero_patrimonial and str(self.numero_patrimonial).strip()
        ):
            raise ValidationError(
                {
                    "numero_patrimonial": "Informe o Número Patrimonial ou marque 'Sem numeração'."
                }
            )

    def _clean_valida_formato_novo(self):
        if (not self.numero_formato_antigo) and (not self.sem_numeracao):
            if not re.fullmatch(NPAT_NUM_REGEX, self.numero_patrimonial or ""):
                raise ValidationError(
                    {"numero_patrimonial": "Número Patrimonial incompleto"}
                )

    def clean(self):
        self._clean_valida_formato_antigo_ou_sem_numeracao()
        self._clean_valida_numero_obrigatorio()
        self._clean_valida_formato_novo()

    def _obter_original_para_auditoria(self):
        if self._state.adding or (self.pk is None):
            return None
        try:
            return type(self).objects.get(pk=self.pk)
        except type(self).DoesNotExist:
            return None

    def _aplicar_sem_numero_auto(self):
        base_id = self.pk
        while True:
            numero_formatado = f"SEM-NUMERO-{base_id}"
            if (
                not type(self)
                .objects.filter(numero_patrimonial=numero_formatado)
                .exists()
            ):
                break
            base_id += 1
        self.numero_patrimonial = numero_formatado
        super(BemPatrimonial, self).save(update_fields=["numero_patrimonial"])

    def _registrar_auditoria_se_alterado(self, original, **kwargs):
        if not original:
            return
        only = kwargs.get("update_fields")
        changes = dict_changes(
            original,
            self,
            fields=self.AUDIT_TRACK_FIELDS,
            only=only,
            ignore=self.AUDIT_IGNORE_FIELDS,
        )
        if not changes:
            return
        ct = ContentType.objects.get_for_model(type(self))
        user = get_user()
        justificativa = getattr(self, "_justificativa", None)
        HistoricoGeral.objects.bulk_create(
            [
                HistoricoGeral(
                    content_type=ct,
                    object_id=str(self.pk),
                    campo=field,
                    valor_antigo=old,
                    valor_novo=new,
                    alterado_por=user,
                    justificativa=justificativa
                )
                for field, (old, new) in changes.items()
            ]
        )

    def save(self, *args, **kwargs):
        original = self._obter_original_para_auditoria()
        gerar_auto = bool(self.sem_numeracao and not self.numero_patrimonial)

        super(BemPatrimonial, self).save(*args, **kwargs)

        if gerar_auto and not self.numero_patrimonial:
            self._aplicar_sem_numero_auto()
        self._registrar_auditoria_se_alterado(original, **kwargs)

    @property
    def pode_solicitar_movimentacao(self):
        return self.status == constants.APROVADO and not self.bloqueado_conciliacao

    @property
    def tem_movimentacao_pendente(self):
        return self.movimentacaobempatrimonial_set.filter(
            status=constants.ENVIADA
        ).exists()

    def set_unidade_administrative(self, unidade):
        self.unidade_administrativa = unidade
        self.save()

    def _on_soft_delete(self):
        from inventario.models import ItemConciliacao
        from inventario import constants as inv_constants

        ItemConciliacao.objects.filter(
            bem_id=self.pk,
            conciliacao__status=inv_constants.CONCILIACAO_EM_ABERTO,
        ).delete()


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
        max_length=50,
        default=constants.AGUARDANDO_APROVACAO,
        null=False,
        blank=False,
    )
    # opcional
    observacao = models.TextField("Observação", blank=True)
    # controle
    atualizado_por = models.ForeignKey(
        Usuario,
        verbose_name="Atualizado por",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    atualizado_em = models.DateTimeField(
        VERBOSE_ATUALIZADO_EM, auto_now=True, blank=True
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
        if self.bem_patrimonial.status != constants.APROVADO:
            self.bem_patrimonial.status = self.status
            self.bem_patrimonial.save()


class MovimentacaoBensItem(models.Model):

    bem = models.ForeignKey(
        BemPatrimonial,
        on_delete=models.CASCADE,
        related_name="movimentacoes_itens",
    )
    movimentacao = models.ForeignKey(
        "MovimentacaoBemPatrimonial",
        on_delete=models.CASCADE,
        related_name="itens",
    )

    class Meta:
        verbose_name = "item de movimentação"
        verbose_name_plural = "itens de movimentação"
        constraints = [
            models.UniqueConstraint(
                fields=["movimentacao", "bem"],
                name="uniq_item_por_movimentacao_bem",
            )
        ]

    def __str__(self):
        return f"Mov#{self.movimentacao_id} • {self.bem}"


class MovimentacaoBemPatrimonial(models.Model):
    "Classe que representa uma solicitacao de movimentacao de um bem patrimonial"

    # obrigatórios
    bem_patrimonial = models.ForeignKey(
        BemPatrimonial,
        verbose_name="Bem patrimonial",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    bens = models.ManyToManyField(
        BemPatrimonial,
        through="MovimentacaoBensItem",
        related_name="movimentacoes",
        verbose_name="Bens patrimoniais",
        blank=True,
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
    observacao = models.TextField("Observacao", blank=True)
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
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField(
        VERBOSE_ATUALIZADO_EM, auto_now=True, blank=True
    )
    numero_cimbpm = models.CharField(
        "Número CIMBPM",
        max_length=30,
        unique=True,
        blank=True,
        default="",
        db_index=True,
    )
    documento_cimbpm = models.FileField(
        "Documento CIMBPM",
        upload_to="documentos_cimbpm/",
        blank=True,
        default="",
        editable=False,
        help_text="PDF gerado automaticamente ao criar movimentação",
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
        return self.status == constants.CANCELADA

    def aprovar_solicitacao(self, usuario):
        if self.aceita or self.status != constants.ENVIADA:
            return

        itens = self.itens.all()

        for item in itens:
            bem = item.bem
            bem.unidade_administrativa = self.unidade_administrativa_destino
            bem.status = constants.APROVADO
            bem.save()

        self.status = constants.ACEITA
        self.aprovado_por = usuario
        self.save()

    def rejeitar_solicitacao(self, usuario):
        if self.rejeitada or self.status != constants.ENVIADA:
            return

        self.status = constants.REJEITADA
        self.rejeitado_por = usuario
        self.save()

        for item in self.itens.all():
            bem = item.bem
            bem.status = constants.APROVADO
            bem.save()

    def cancelar_solicitacao(self, usuario):
        if self.cancelada or self.status != constants.ENVIADA:
            return

        self.status = constants.CANCELADA
        self.cancelado_por = usuario
        self.save()

        for item in self.itens.all():
            bem = item.bem
            bem.status = constants.APROVADO
            bem.save()


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


@receiver(post_save, sender=MovimentacaoBensItem)
def bloquear_bem_quando_item_criado(sender, instance, created, **kwargs):
    if not created:
        return

    movimentacao = instance.movimentacao
    bem = instance.bem

    if movimentacao.status != constants.ENVIADA:
        return

    if bem.status == constants.BLOQUEADO:
        return

    bem.status = constants.BLOQUEADO
    bem.save(update_fields=["status"])


@receiver(post_save, sender=MovimentacaoBemPatrimonial)
def envia_email_alert_nova_solicitacao(sender, instance, created, **kwargs):
    if created:
        emails = []
        usuarios = (
            Usuario.objects.filter(
                is_active=True,
                unidades_administrativas=instance.unidade_administrativa_destino,
            )
            .distinct()
            .only("email")
        )
        for usuario in usuarios:
            if usuario.email:
                emails.append(usuario.email)

        envia_email_nova_solicitacao_movimentacao(instance, emails)


@receiver(post_save, sender=MovimentacaoBemPatrimonial)
def gerar_numero_cimbpm_signal(sender, instance, created, **kwargs):
    if created:
        from bem_patrimonial.cimbpm import gerar_numero_cimbpm

        if not instance.numero_cimbpm:
            instance.numero_cimbpm = gerar_numero_cimbpm(instance)
            instance.save(update_fields=["numero_cimbpm"])


@receiver(pre_save, sender=BemPatrimonial)
def bempatrimonial_guardar_estado_anterior(sender, instance, **kwargs):
    """
    Captura o old_ua_id antes de salvar, para o post_save conseguir:
    - remover o bem da conciliação EM ABERTO da UA antiga
    - incluir/atualizar na conciliação EM ABERTO da UA nova
    Funciona para qualquer origem (admin, API, services, scripts, etc.)
    """
    if not instance.pk:
        instance._old_ua_id = None
        return

    old = (
        BemPatrimonial.all_objects.filter(pk=instance.pk)
        .only("unidade_administrativa_id")
        .first()
    )

    instance._old_ua_id = getattr(old, "unidade_administrativa_id", None)


@receiver(post_save, sender=BemPatrimonial)
def bempatrimonial_sync_conciliacao_em_aberto(sender, instance, created, **kwargs):
    """
    Executa o sync somente após commit para garantir consistência.
    Usa o _old_ua_id capturado no pre_save (inclusive fora do admin).
    """
    old_ua_id = getattr(instance, "_old_ua_id", None)

    def _run():
        from inventario.services.conciliacao_sync import sync_bem_pos_save

        sync_bem_pos_save(instance, old_ua_id=old_ua_id)

    transaction.on_commit(_run)


class BaixaFisicaBemPatrimonial(models.Model):
    """
    Registro de Baixa Física de bens em uma Unidade Administrativa.
    Similar à MovimentacaoBemPatrimonial, mas muda só status do bem.
    """

    unidade_administrativa_origem = models.ForeignKey(
        UnidadeAdministrativa,
        related_name="baixas_fisicas_origem",
        verbose_name="Unidade administrativa",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )

    numero_processo_baixa = models.CharField(
        "Número do processo de Baixa Física",
        max_length=64,
        null=False,
        blank=False,
    )

    status = models.CharField(
        "Status",
        choices=constants.STATUS_BAIXA_FISICA,
        max_length=30,
        default=constants.AGUARDANDO_ENVIO,
        null=False,
        blank=False,
    )

    criado_por = models.ForeignKey(
        Usuario,
        verbose_name="Usuário que realizou a baixa",
        related_name="baixas_fisicas_criadas",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
    )

    data_criacao = models.DateTimeField(
        "Data/hora da solicitação de baixa",
        auto_now_add=True,
    )

    data_baixa = models.DateField(
        "Data da Baixa Física",
        default=timezone.now,
        help_text="Data informada no processo de baixa física",
    )

    aprovado_por = models.ForeignKey(
        Usuario,
        verbose_name="Gestor que aprovou a baixa",
        related_name="baixas_fisicas_aprovadas",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )

    data_aprovacao = models.DateTimeField(
        "Data/hora da aprovação",
        null=True,
        blank=True,
    )

    numero_nbbpm = models.CharField(
        max_length=32, blank=True, default="", db_index=True
    )

    class Meta:
        verbose_name = "Baixa Física de Bem Patrimonial"
        verbose_name_plural = "Baixas Físicas de Bens Patrimoniais"

    def __str__(self):
        return f"Baixa Física #{self.pk} - UA: {self.unidade_administrativa_origem}"

    def _clean_valida_data_baixa(self):
        if not self.data_baixa:
            return
        data_baixa = (
            self.data_baixa.date()
            if hasattr(self.data_baixa, "date")
            else self.data_baixa
        )
        if data_baixa > timezone.localdate():
            raise ValidationError(
                {
                    "data_baixa": "A data da Baixa Física não pode ser maior que a data atual."
                }
            )

    def _clean_valida_itens_baixa(self, itens):
        for item in itens:
            bem = item.bem
            if bem.unidade_administrativa_id != self.unidade_administrativa_origem_id:
                raise ValidationError(
                    f"O bem '{bem}' não pertence à Unidade Administrativa selecionada."
                )
            if bem.status == constants.BAIXA_FISICA:
                raise ValidationError(f"O bem '{bem}' já foi baixado.")
            if BaixaFisicaBensItem.objects.filter(
                bem=bem,
                baixa__status__in=[
                    constants.AGUARDANDO_ENVIO,
                    constants.SOLICITADA,
                    constants.ACEITA,
                ],
            ).exclude(baixa=self).exists():
                raise ValidationError(
                    f"O bem '{bem}' já está em processo de Baixa Física em outro pedido."
                )

    def clean(self):
        super().clean()
        self._clean_valida_data_baixa()
        if not self.numero_processo_baixa:
            raise ValidationError(
                {
                    "numero_processo_baixa": "Informe o número do processo de Baixa Física."
                }
            )
        if not self.pk:
            return
        itens = list(self.itens.select_related("bem", "bem__unidade_administrativa"))
        if not itens:
            raise ValidationError("Não é possível manter uma Baixa Física sem itens.")
        self._clean_valida_itens_baixa(itens)

    @transaction.atomic
    def enviar_solicitacao(self):
        """
        Confirma a baixa (coloca como ENVIADA) e
        marca os bens como 'Baixa Física - Aguardando aprovação'.
        """
        if not self.itens.exists():
            raise ValidationError("Não é possível enviar Baixa Física sem itens.")

        self.status = constants.SOLICITADA
        self.save(update_fields=["status"])

        for item in self.itens.select_related("bem"):
            bem = item.bem

            bem.status = constants.BAIXA_FISICA_AGUARDANDO_APROVACAO
            bem.save(update_fields=["status"])

    @transaction.atomic
    def aprovar(self, usuario_aprovador):
        """
        Aprova a Baixa Física:
        - status da baixa => ACEITA
        - status do bem => BAIXA_FISICA
        - limpa 'numero_processo' (incorporação)
        """
        if self.status != constants.SOLICITADA:
            raise ValidationError(
                "Só é possível aprovar baixas com status 'Solicitada'."
            )

        self.status = constants.ACEITA
        self.aprovado_por = usuario_aprovador
        self.data_aprovacao = timezone.now()
        self.save(update_fields=["status", "aprovado_por", "data_aprovacao"])
        texto_localizacao = f"Baixa Física - {self.numero_processo_baixa}"

        for item in self.itens.select_related("bem"):
            bem = item.bem
            bem.status = constants.BAIXA_FISICA
            bem.localizacao = texto_localizacao
            bem.numero_processo = None
            bem.save(update_fields=["status", "numero_processo", "localizacao"])


class BaixaFisicaBensItem(models.Model):
    bem = models.ForeignKey(
        BemPatrimonial,
        on_delete=models.CASCADE,
        related_name="baixas_fisicas_itens",
    )
    baixa = models.ForeignKey(
        BaixaFisicaBemPatrimonial,
        on_delete=models.CASCADE,
        related_name="itens",
    )

    class Meta:
        verbose_name = "item de baixa física"
        verbose_name_plural = "itens de baixa física"
        unique_together = ("bem", "baixa")

    def __str__(self):
        return f"{self.bem} (Baixa #{self.baixa_id})"
