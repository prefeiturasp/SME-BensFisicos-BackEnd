from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from datetime import date

from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria
from usuario.models import Usuario

from . import constants


class ParametroConciliacaoAnual(models.Model):
    unidade_orcamentaria = models.ForeignKey(
        UnidadeOrcamentaria,
        on_delete=models.PROTECT,
        related_name="parametros_conciliacao_anual",
        verbose_name="Unidade Orçamentária",
    )
    
    ano_referencia = models.PositiveSmallIntegerField(
        "Ano de Referência",
        help_text="Ano da conciliação anual ao qual este parâmetro se refere (ex.: 2025).",
    )

    periodo_inicial = models.DateField(
        "Período Inicial Permitido",
        help_text="Data inicial em que conciliações anuais podem ser criadas/fechadas.",
    )

    periodo_final = models.DateField(
        "Período Final Permitido",
        help_text="Data final em que conciliações anuais podem ser criadas/fechadas.",
    )

    ativo = models.BooleanField(
        "Ativo",
        default=True,
        help_text="Apenas um parâmetro ativo por ano.",
    )

    class Meta:
        verbose_name = "Parâmetro de Conciliação Anual"
        verbose_name_plural = "Parâmetros de Conciliação Anual"
        constraints = [
            models.UniqueConstraint(
                fields=["unidade_orcamentaria", "ano_referencia"],
                condition=Q(ativo=True),
                name="unique_parametro_conciliacao_anual_ativo_por_uo_ano",
            )
        ]
        ordering = ["-ano_referencia", "-periodo_inicial"]

    def __str__(self):
        return (
            f"{self.ano_referencia} | "
            f"{self.periodo_inicial:%d/%m/%Y} → {self.periodo_final:%d/%m/%Y}"
        )

    def clean(self):
        super().clean()

        if not self.periodo_inicial or not self.periodo_final:
            raise ValidationError("Período inicial e período final são obrigatórios.")

        if self.periodo_inicial > self.periodo_final:
            raise ValidationError(
                {
                    "periodo_final": "O período final deve ser maior ou igual ao período inicial."
                }
            )

        conflito = ParametroConciliacaoAnual.objects.filter(
            ano_referencia=self.ano_referencia
        ).exclude(pk=self.pk)

        conflito = conflito.filter(
            Q(periodo_inicial__lte=self.periodo_final)
            & Q(periodo_final__gte=self.periodo_inicial)
        )

        if conflito.exists():
            raise ValidationError(
                "Já existe um período cadastrado que se sobrepõe a este intervalo."
            )

        if self.ativo:
            ja_ativo = ParametroConciliacaoAnual.objects.filter(
                ano_referencia=self.ano_referencia,
                ativo=True,
            ).exclude(pk=self.pk)

            if ja_ativo.exists():
                raise ValidationError("Já existe um parâmetro ativo para este ano.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def esta_vigente(self):
        """
        Indica se o período está em aberto no dia atual.
        """
        hoje = timezone.localdate()
        return self.periodo_inicial <= hoje <= self.periodo_final


class ConciliacaoUA(models.Model):

    numero_conciliacao = models.CharField(
        "Número do Conciliação",
        max_length=30,
        help_text="Formato: 001.XXXX/AAAA (anual) ou 001.XXXX/AAAA/VVV (eventual)",
    )

    periodo_final = models.DateField(
        "Período Final",
        null=True,
        blank=True,
        help_text="Data final do período da conciliação.",
    )

    tipo = models.CharField(
        "Tipo",
        max_length=20,
        choices=constants.TIPOS_CONCILIACAO,
    )

    unidade_administrativa = models.ForeignKey(
        UnidadeAdministrativa,
        on_delete=models.PROTECT,
        related_name="conciliacoes",
        verbose_name="Unidade Administrativa",
    )

    status = models.CharField(
        "Status",
        max_length=20,
        choices=constants.STATUS_CONCILIACAO,
        default=constants.CONCILIACAO_EM_ABERTO,
    )

    criado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="conciliacoes_criadas",
        verbose_name="Criado por",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)

    fechado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="conciliacoes_fechadas",
        verbose_name="Fechado por",
    )
    fechado_em = models.DateTimeField("Fechado em", null=True, blank=True)

    class Meta:

        verbose_name = "Conciliação"
        verbose_name_plural = "Conciliações"
        ordering = ["-criado_em", "unidade_administrativa"]

        indexes = [
            models.Index(fields=["unidade_administrativa", "tipo"]),
            models.Index(fields=["unidade_administrativa", "periodo_final"]),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=["unidade_administrativa", "tipo", "periodo_final"],
                name="uniq_conciliacao_ua_tipo_periodo_final",
            ),
        ]

    def __str__(self):
        return f"{self.numero_conciliacao} - {self.unidade_administrativa.sigla}"

    def _get_ano_referencia(self):
        """
        EVENTUAL:
        - ano vem do periodo_final (se existir)
        ANUAL:
        - sempre o ano anterior ao ano corrente
        """
        hoje = timezone.localdate()

        if self.tipo == constants.CONCILIACAO_EVENTUAL:
            if self.periodo_final:
                return self.periodo_final.year
            return hoje.year

        return hoje.year - 1

    def _get_proxima_versao_eventual(self):
        ano = self._get_ano_referencia()
        qs = ConciliacaoUA.objects.filter(
            unidade_administrativa=self.unidade_administrativa,
            tipo=constants.CONCILIACAO_EVENTUAL,
            periodo_final__year=ano,
        )

        if self.pk:
            qs = qs.exclude(pk=self.pk)

        return qs.count() + 1

    def _validar_unicidade_conciliacao_anual(self):
        if self.tipo != constants.CONCILIACAO_ANUAL:
            return

        if not self.unidade_administrativa_id:
            return

        if self.pk:
            return

        ano = self._get_ano_referencia()

        existe = ConciliacaoUA.objects.filter(
            unidade_administrativa=self.unidade_administrativa,
            tipo=constants.CONCILIACAO_ANUAL,
            periodo_final=date(ano, 12, 31),
        ).exists()

        if existe:
            raise ValidationError(
                {
                    "tipo": (
                        f"Já existe uma conciliação anual para o ano de referência "
                        f"{ano} nesta Unidade Administrativa."
                    )
                }
            )

    def _validar_parametro_anual_por_data_atual(self):
        if self.tipo != constants.CONCILIACAO_ANUAL:
            return

        if self.pk:
            return

        hoje = timezone.localdate()
        ano_referencia = self._get_ano_referencia()
        ano_corrente = hoje.year

        from .models import ParametroConciliacaoAnual

        uo_id = getattr(self.unidade_administrativa, "unidade_orcamentaria_id", None)
        if not uo_id:
            raise ValidationError(
                {"unidade_administrativa": "UA sem Unidade Orçamentária vinculada."}
            )
        parametro = ParametroConciliacaoAnual.objects.filter(
            unidade_orcamentaria_id=uo_id,
            ano_referencia=ano_referencia,
            ativo=True,
        ).first()

        if parametro:
            data_inicio = parametro.periodo_inicial
            data_fim = parametro.periodo_final
        else:
            data_inicio = timezone.datetime(year=ano_corrente, month=1, day=1).date()
            data_fim = timezone.datetime(year=ano_corrente, month=3, day=31).date()

        if not (data_inicio <= hoje <= data_fim):
            raise ValidationError(
                f"A conciliação anual {ano_referencia} só pode ser criada entre "
                f"{data_inicio:%d/%m/%Y} e {data_fim:%d/%m/%Y}."
            )

    def clean(self):
        super().clean()

        if not self.tipo:
            raise ValidationError({"tipo": "Campo obrigatório."})

        if self.tipo == constants.CONCILIACAO_EVENTUAL and not self.periodo_final:
            raise ValidationError(
                {"periodo_final": "Campo obrigatório para conciliação eventual."}
            )

        if self.tipo == constants.CONCILIACAO_ANUAL:
            ano_referencia = self._get_ano_referencia()
            self.periodo_final = date(ano_referencia, 12, 31)

        self._validar_unicidade_conciliacao_anual()
        self._validar_parametro_anual_por_data_atual()

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["numero_conciliacao"])

        if not self.numero_conciliacao:
            if not self.unidade_administrativa_id:
                raise ValidationError(
                    {"unidade_administrativa": "Unidade Administrativa é obrigatória."}
                )

            codigo = self.unidade_administrativa.codigo.replace(".", "")[-4:]
            ano = self._get_ano_referencia()

            if self.tipo == constants.CONCILIACAO_EVENTUAL:
                versao = self._get_proxima_versao_eventual()
                self.numero_conciliacao = f"001.{codigo}/{ano}/{versao:03d}"
            else:
                self.numero_conciliacao = f"001.{codigo}/{ano}"

        super().save(*args, **kwargs)

    def finalizar(self, usuario):
        if self.status == constants.CONCILIACAO_FECHADO:
            return

        self.status = constants.CONCILIACAO_FECHADO
        self.fechado_por = usuario
        self.fechado_em = timezone.now()
        self.save(update_fields=["status", "fechado_por", "fechado_em"])

    @property
    def esta_aberto(self):
        return self.status == constants.CONCILIACAO_EM_ABERTO


class ItemConciliacao(models.Model):

    conciliacao = models.ForeignKey(
        ConciliacaoUA,
        on_delete=models.CASCADE,
        related_name="itens",
        verbose_name="Conciliação",
    )

    bem = models.ForeignKey(
        "bem_patrimonial.BemPatrimonial",
        on_delete=models.PROTECT,
        related_name="itens_conciliacao",
        verbose_name="Bem Patrimonial",
    )

    situacao = models.CharField(
        "Situação",
        max_length=30,
        choices=constants.SITUACOES_ITEM_CONCILIACAO,
        default=constants.ENCONTRADO_SEM_DIVERGENCIA,
        help_text="Situação do bem no momento da criação da conciliação",
    )

    observacao = models.TextField(
        "Observação",
        blank=True,
        help_text="Observações sobre o item (opcional)",
    )

    divergencia = models.TextField(
        "Divergência",
        blank=True,
        help_text="Descrição da divergência (obrigatório quando situação = Divergente)",
    )

    atualizado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        related_name="itens_atualizados",
        verbose_name="Atualizado por",
    )
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        unique_together = ("conciliacao", "bem")
        verbose_name = "Item de Conciliação"
        verbose_name_plural = "Itens de Conciliação"
        ordering = ["bem__numero_patrimonial"]

        indexes = [
            models.Index(fields=["conciliacao", "bem"]),
            models.Index(fields=["bem"]),
            models.Index(fields=["situacao"]),
        ]

    def __str__(self):
        return f"{self.bem.numero_patrimonial} - {self.get_situacao_display()}"

    def clean(self):
        super().clean()

        if self.situacao == constants.DIVERGENTE and not self.divergencia:
            raise ValidationError(
                {"divergencia": "Campo obrigatório quando situação é Divergente"}
            )

        if self.situacao != constants.DIVERGENTE and self.divergencia:
            raise ValidationError(
                {
                    "divergencia": "Preencha divergência apenas quando a situação for Divergente."
                }
            )

    @property
    def tem_ocorrencia(self):
        return self.ocorrencias.exists()

    @property
    def pode_marcar_como_encontrado(self):
        return (
            not self.ocorrencias.exists() and self.situacao == constants.NAO_ENCONTRADO
        )

    @property
    def pode_resolver_situacao(self):
        return not self.ocorrencias.exists() and self.situacao == constants.DIVERGENTE

    @property
    def permite_registrar_ocorrencia(self):
        if self.situacao == constants.BAIXA_FISICA:
            return False
        return True


class OcorrenciaConciliacao(models.Model):

    item = models.ForeignKey(
        ItemConciliacao,
        on_delete=models.CASCADE,
        related_name="ocorrencias",
        verbose_name="Item de Conciliação",
    )

    situacao = models.CharField(
        "Situação",
        max_length=30,
        choices=constants.SITUACOES_ITEM_CONCILIACAO,
        default=constants.DIVERGENTE,
        help_text="Situação na ocorrencia",
    )

    observacao = models.TextField("Observação", blank=True)
    divergencia = models.TextField("Divergência", blank=True)

    registrado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        verbose_name="Registrado por",
    )
    registrado_em = models.DateTimeField("Registrado em", auto_now_add=True)

    class Meta:
        ordering = ["-registrado_em"]
        verbose_name = "Ocorrência de Conciliação"
        verbose_name_plural = "Ocorrências de Conciliação"

        indexes = [
            models.Index(fields=["item", "registrado_em"]),
        ]

    def __str__(self):
        return f"{self.item.bem.numero_patrimonial} - {self.get_situacao_display()}"
