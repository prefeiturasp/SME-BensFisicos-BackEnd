from django.dispatch import receiver
from django.db.models.signals import post_save
from datetime import datetime
from django.db import models
from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario

ORIGENS = (
    (1, "Repasse de verba"),
    (2, "Aquisição direta"),
    (3, "Transferência"),
    (4, "Movimentação"),
)

AGUARDANDO_APROVACAO = 1
APROVADO = 2
NAO_APROVADO = 3

STATUS = (
    (AGUARDANDO_APROVACAO, "Aguardando aprovação"),
    (APROVADO, "Aprovado"),
    (NAO_APROVADO, "Não aprovado"),
)

ENVIADA = 1
ACEITA = 2
REJEITADA = 3

STATUS_SOLICITACAO_MOVIMENTACAO = (
    (ENVIADA, "Enviada"),
    (ACEITA, "Aceita"),
    (REJEITADA, "Rejeitada"),
)


class BemPatrimonial(models.Model):
    "Classe que representa um bem patrimonial"
    # obrigatórios
    nome = models.CharField("Nome do bem", max_length=255, null=False, blank=False)
    data_compra_entrega = models.DateField("Data da compra/entrega", null=False, blank=False)
    origem = models.PositiveIntegerField("Origem", choices=ORIGENS, null=False, blank=False)
    marca = models.CharField("Marca", max_length=255, null=False, blank=False)
    modelo = models.CharField("Modelo", max_length=255, null=False, blank=False)
    quantidade = models.PositiveIntegerField("Quantidade", null=False, blank=False)
    descricao = models.TextField("Descrição", null=False, blank=False)
    valor_unitario = models.DecimalField("Valor unitário", max_digits=16, decimal_places=2, blank=False, null=False)
    numero_processo = models.PositiveIntegerField("Número do processo de incorporação/transferência", null=False, blank=False)
    status = models.PositiveIntegerField("Status", choices=STATUS, default=AGUARDANDO_APROVACAO,
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
        if self.status is APROVADO:
            return True
        return False

    def atualizar_historico_unidade_administrativa(self, unidade, solicitacao=None):
        self.unidade_administrativa = unidade
        self.historicomovimentacaobempatrimonial_set.create(
            unidade_administrativa=unidade,
            solicitacao_movimentacao=solicitacao
        )
        self.save()


class HistoricoStatusBemPatrimonial(models.Model):
    "Classe que representa o histórico de mudança de status do bem patrimonial"
    bem_patrimonial = models.ForeignKey(BemPatrimonial, verbose_name="Bem patrimonial", on_delete=models.CASCADE,
                                        null=True, blank=True)
    status = models.PositiveIntegerField("Status", choices=STATUS, default=AGUARDANDO_APROVACAO,
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
        return super(HistoricoStatusBemPatrimonial, self).save(*args, **kwargs)

    def __str__(self) -> str:
        return str(self.pk)

    class Meta:
        verbose_name = 'histórico de status'
        verbose_name_plural = 'histórico de status'

    def sincroniza_status_bem_patrimonial(self):
        self.bem_patrimonial.status = self.status
        self.bem_patrimonial.save()


class SolicitacaoMovimentacaoBemPatrimonial(models.Model):
    "Classe que representa uma solicitacao de movimentacao de um bem patrimonial"
    # obrigatórios
    bem_patrimonial = models.ForeignKey(BemPatrimonial, verbose_name="Bem patrimonial", on_delete=models.CASCADE,
                                        null=False, blank=False)
    unidade_administrativa_destino = models.ForeignKey(UnidadeAdministrativa, verbose_name="Unidade administrativa destino",
                                                       on_delete=models.CASCADE, null=False, blank=False)
    status = models.PositiveIntegerField("Status", choices=STATUS_SOLICITACAO_MOVIMENTACAO, default=ENVIADA,
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
        verbose_name = 'solicitação de movimentação de bem patrimonial'
        verbose_name_plural = 'solicitações de movimentação de bem patrimonial'

    def save(self, *args, **kwargs):
        self.atualizado_em = datetime.now()
        return super(SolicitacaoMovimentacaoBemPatrimonial, self).save(*args, **kwargs)

    def aprovar_solicitacao_e_atualizar_historico(self, usuario):
        if self.status is not ACEITA:
            self.status = ACEITA
            self.aprovado_por = usuario
            self.save()

            self.bem_patrimonial.atualizar_historico_unidade_administrativa(
                self.unidade_administrativa_destino,
                self
            )

    def rejeitar_solicitacao(self, usuario):
        if self.status is not REJEITADA:
            self.status = REJEITADA
            self.rejeitado_por = usuario
            self.save()


class HistoricoMovimentacaoBemPatrimonial(models.Model):
    "Classe que representa uma solicitacao de movimentacao de um bem patrimonial"
    # obrigatórios
    bem_patrimonial = models.ForeignKey(BemPatrimonial, verbose_name="Bem patrimonial", on_delete=models.CASCADE,
                                        null=False, blank=False)
    unidade_administrativa = models.ForeignKey(UnidadeAdministrativa, verbose_name="Unidade administrativa",
                                               on_delete=models.CASCADE, null=False, blank=False)
    solicitacao_movimentacao = models.ForeignKey(SolicitacaoMovimentacaoBemPatrimonial, verbose_name="Solicitação de movimentação",
                                                 on_delete=models.SET_NULL, null=True, blank=True)
    criado_em = models.DateTimeField("Criado em", auto_now=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True, null=True, blank=True)

    def __str__(self) -> str:
        return str(self.pk)

    class Meta:
        verbose_name = 'histórico de movimentação de bem patrimonial'
        verbose_name_plural = 'históricos de movimentação de bem patrimonial'

    def save(self, *args, **kwargs):
        self.atualizado_em = datetime.now()
        return super(HistoricoMovimentacaoBemPatrimonial, self).save(*args, **kwargs)


@receiver(post_save, sender=BemPatrimonial)
def cria_primeiro_historico_status(sender, instance, created, **kwargs):
    if created:
        instance.historicostatusbempatrimonial_set.create(
            status=AGUARDANDO_APROVACAO,
            atualizado_por=instance.criado_por
        )


@receiver(post_save, sender=BemPatrimonial)
def cria_primeiro_historico_movimentacao(sender, instance, created, **kwargs):
    if created:
        instance.atualizar_historico_unidade_administrativa(
            instance.criado_por.unidade_administrativa
        )
