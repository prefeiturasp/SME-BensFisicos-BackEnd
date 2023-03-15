from datetime import datetime
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.db import models
from django.core.exceptions import ObjectDoesNotExist

from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario
from bem_patrimonial.emails import envia_email_nova_solicitacao_movimentacao, envia_email_cadastro_nao_aprovado
from bem_patrimonial import constants


class BemPatrimonial(models.Model):
    "Classe que representa um bem patrimonial"
    # obrigatórios
    nome = models.CharField("Nome do bem", max_length=255, null=False, blank=False)
    data_compra_entrega = models.DateField("Data da compra/entrega", null=False, blank=False)
    origem = models.CharField("Origem", max_length=30, choices=constants.ORIGENS, null=False, blank=False)
    marca = models.CharField("Marca", max_length=255, null=False, blank=False)
    modelo = models.CharField("Modelo", max_length=255, null=False, blank=False)
    quantidade = models.PositiveIntegerField("Quantidade", null=False, blank=False)
    descricao = models.TextField("Descrição", null=False, blank=False)
    valor_unitario = models.DecimalField("Valor unitário", max_digits=16, decimal_places=2, blank=False, null=False)
    numero_processo = models.PositiveIntegerField("Número do processo de incorporação/transferência", null=False, blank=False)
    status = models.CharField("Status", max_length=30, choices=constants.STATUS, default=constants.AGUARDANDO_APROVACAO,
                              null=False, blank=False)
    unidade_administrativa = models.ForeignKey(UnidadeAdministrativa, on_delete=models.SET_NULL,
                                               null=True, blank=True)
    # opcionais
    autorizacao_no_doc_em = models.DateField("Autorização no DOC em", null=True, blank=True)
    numero_nibpm = models.PositiveIntegerField("Número NIBPM", null=True, blank=True)
    numero_cimbpm = models.PositiveIntegerField("Número CIMBPM", null=True, blank=True)
    numero_patrimonial = models.PositiveIntegerField("Número Patrimonial", null=True, blank=True)
    localizacao = models.CharField("Localização", max_length=255, null=True, blank=True)
    numero_serie = models.PositiveIntegerField("Número de série", null=True, blank=True)
    # controle
    criado_por = models.ForeignKey(Usuario, verbose_name="Criado por", on_delete=models.SET_NULL,
                                   null=True, blank=True)
    criado_em = models.DateTimeField("Criado em", auto_now=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True, null=True, blank=True)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = 'bem patrimonial'
        verbose_name_plural = 'bens patrimoniais'

    def save(self, *args, **kwargs):
        self.atualizado_em = datetime.now()
        return super(BemPatrimonial, self).save(*args, **kwargs)

    @property
    def pode_solicitar_movimentacao(self):
        if self.status is constants.APROVADO:
            return True
        return False

    def set_unidade_administrative(self, unidade):
        self.unidade_administrativa = unidade
        self.save()


class StatusBemPatrimonial(models.Model):
    "Classe que representa o histórico de mudança de status do bem patrimonial"
    bem_patrimonial = models.ForeignKey(BemPatrimonial, verbose_name="Bem patrimonial", on_delete=models.CASCADE,
                                        null=True, blank=True)
    status = models.CharField("Status", choices=constants.STATUS, max_length=30, default=constants.AGUARDANDO_APROVACAO,
                              null=False, blank=False)
    # opcional
    observacao = models.TextField("Observação", null=True, blank=True)
    # controle
    atualizado_por = models.ForeignKey(Usuario, verbose_name="Atualizado por", on_delete=models.SET_NULL,
                                       null=True, blank=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True, null=True, blank=True)

    def save(self, *args, **kwargs):
        self.atualizado_em = datetime.now()
        self.sincroniza_status_bem_patrimonial()
        return super(StatusBemPatrimonial, self).save(*args, **kwargs)

    def __str__(self) -> str:
        return str(self.pk)

    class Meta:
        verbose_name = 'status do bem patrimonial'
        verbose_name_plural = 'histórico status do bem patrimonial'

    def sincroniza_status_bem_patrimonial(self):
        if self.bem_patrimonial.status is not constants.APROVADO:
            self.bem_patrimonial.status = self.status
            self.bem_patrimonial.save()


class UnidadeAdministrativaBemPatrimonial(models.Model):
    "Classe que representa a quantidade de bem patrimonial por unidade administrativa."

    bem_patrimonial = models.ForeignKey(BemPatrimonial, verbose_name="Bem patrimonial", on_delete=models.CASCADE,
                                        null=False, blank=False)
    unidade_administrativa = models.ForeignKey(UnidadeAdministrativa, verbose_name="Unidade administrativa", on_delete=models.CASCADE,
                                               null=False, blank=False)
    quantidade = models.PositiveIntegerField("Quantidade", default=1, null=False, blank=False)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True, null=True, blank=True)

    def __str__(self) -> str:
        return str(self.pk)

    class Meta:
        verbose_name = 'bem patrimonial por unidade administrativa'
        verbose_name_plural = 'bens patrimoniais por unidade administrativa'

    def save(self, *args, **kwargs):
        self.atualizado_em = datetime.now()
        return super(UnidadeAdministrativaBemPatrimonial, self).save(*args, **kwargs)

    def remover_quantidade(self, quantidade):
        self.quantidade = self.quantidade - quantidade
        self.save()

    def adicionar_quantidade(self, quantidade):
        self.quantidade = self.quantidade + quantidade
        self.save()


class MovimentacaoBemPatrimonial(models.Model):
    "Classe que representa uma solicitacao de movimentacao de um bem patrimonial"
    # obrigatórios
    bem_patrimonial = models.ForeignKey(BemPatrimonial, verbose_name="Bem patrimonial", on_delete=models.CASCADE,
                                        null=False, blank=False)
    unidade_administrativa_origem = models.ForeignKey(UnidadeAdministrativa, related_name='%(class)s_origem', verbose_name="Unidade administrativa origem",
                                                      on_delete=models.CASCADE, null=False, blank=False)
    unidade_administrativa_destino = models.ForeignKey(UnidadeAdministrativa, related_name='%(class)s_destino', verbose_name="Unidade administrativa destino",
                                                       on_delete=models.CASCADE, null=False, blank=False)
    quantidade = models.PositiveIntegerField("Quantidade", default=1, null=False, blank=False)
    status = models.CharField("Status", choices=constants.STATUS_MOVIMENTACAO, max_length=30, default=constants.ENVIADA,
                              null=False, blank=False)
    observacao = models.TextField("Observacao", null=True, blank=True)
    # controle
    solicitado_por = models.ForeignKey(Usuario, verbose_name="Solicitado por", related_name='%(class)s_solicitadopor', on_delete=models.DO_NOTHING,
                                       null=False, blank=False)
    aprovado_por = models.ForeignKey(Usuario, verbose_name="Aprovado por", related_name='%(class)s_aprovadopor', on_delete=models.SET_NULL,
                                     null=True, blank=True)
    rejeitado_por = models.ForeignKey(Usuario, verbose_name="Rejeitado por", related_name='%(class)s_rejeitadopor', on_delete=models.SET_NULL,
                                      null=True, blank=True)
    criado_em = models.DateTimeField("Criado em", auto_now=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True, null=True, blank=True)

    def __str__(self) -> str:
        return "Solicitação #{}".format(str(self.pk))

    class Meta:
        verbose_name = 'movimentação de bem patrimonial'
        verbose_name_plural = 'movimentações de bem patrimonial'

    def save(self, *args, **kwargs):
        if not self.atualizado_em:
            self.atualizado_em = datetime.now()
        return super(MovimentacaoBemPatrimonial, self).save(*args, **kwargs)

    @property
    def aceita(self):
        return self.status is constants.ACEITA

    @property
    def rejeitada(self):
        return self.status is constants.REJEITADA

    def aprovar_solicitacao(self, usuario):
        if not self.aceita:
            try:
                bem_patrimonial_por_unidade_origem = self.bem_patrimonial.unidadeadministrativabempatrimonial_set.get(
                    unidade_administrativa=self.unidade_administrativa_origem
                )
            except Exception:
                raise ObjectDoesNotExist

            bem_patrimonial_por_unidade_destino, created = self.bem_patrimonial.unidadeadministrativabempatrimonial_set.get_or_create(
                unidade_administrativa=self.unidade_administrativa_destino,
                defaults={
                    'quantidade': self.quantidade
                }
            )
            if not created:
                bem_patrimonial_por_unidade_destino.adicionar_quantidade(self.quantidade)

            bem_patrimonial_por_unidade_origem.remover_quantidade(self.quantidade)

            self.status = constants.ACEITA
            self.aprovado_por = usuario
            self.save()

    def rejeitar_solicitacao(self, usuario):
        if not self.rejeitada:
            self.status = constants.REJEITADA
            self.rejeitado_por = usuario
            self.save()


@receiver(post_save, sender=BemPatrimonial)
def cria_primeiro_status_bem_patrimonial(sender, instance, created, **kwargs):
    if created and instance.status is constants.AGUARDANDO_APROVACAO:
        instance.statusbempatrimonial_set.create(
            status=constants.AGUARDANDO_APROVACAO,
            atualizado_por=instance.criado_por
        )


@receiver(post_save, sender=BemPatrimonial)
def cria_registro_unidade_administrativa_bem_patrimonial(sender, instance, created, **kwargs):
    if created:
        instance.unidadeadministrativabempatrimonial_set.create(
            unidade_administrativa=instance.criado_por.unidade_administrativa,
            quantidade=instance.quantidade
        )


@receiver(post_save, sender=StatusBemPatrimonial)
def envia_email_status_reprovado(sender, instance, created, **kwargs):
    if not created and (instance.status is constants.NAO_APROVADO):
        envia_email_cadastro_nao_aprovado(instance)


@receiver(post_save, sender=MovimentacaoBemPatrimonial)
def envia_email_alert_nova_solicitacao(sender, instance, created, **kwargs):
    if created:
        # pega emails dos usuários do setor destino
        emails = []
        usuarios = Usuario.objects.filter(
            is_active=True,
            unidade_administrativa=instance.unidade_administrativa_destino
        ).only('email')
        for usuario in usuarios:
            emails.append(usuario.email)

        envia_email_nova_solicitacao_movimentacao(instance.bem_patrimonial, emails)
