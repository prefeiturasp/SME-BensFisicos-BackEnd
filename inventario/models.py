from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from bem_patrimonial.models import BemPatrimonial
from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario

from . import constants


class ParametroInventarioAnual(models.Model):

    ano_referencia = models.PositiveSmallIntegerField(
        "Ano de Referência",
        help_text="Ano do inventário anual ao qual este parâmetro se refere (ex.: 2025).",
    )

    periodo_inicial = models.DateField(
        "Período Inicial Permitido",
        help_text="Data inicial em que inventários anuais podem ser criados/fechados.",
    )

    periodo_final = models.DateField(
        "Período Final Permitido",
        help_text="Data final em que inventários anuais podem ser criados/fechados.",
    )

    ativo = models.BooleanField(
        "Ativo",
        default=True,
        help_text="Apenas um parâmetro ativo por ano.",
    )

    class Meta:
        verbose_name = "Parâmetro de Inventário Anual"
        verbose_name_plural = "Parâmetros de Inventário Anual"
        constraints = [
            models.UniqueConstraint(
                fields=["ano_referencia"],
                condition=models.Q(ativo=True),
                name="unique_parametro_inventario_anual_ativo_por_ano",
            )
        ]


class InventarioUA(models.Model):

    numero_inventario = models.CharField(
        "Número do Inventário",
        max_length=30,
        unique=True,
        help_text="Formato: 001.XXXX/AAAA (anual) ou 001.XXXX/AAAA/VVV (eventual)",
    )

    periodo_final = models.DateField(
        "Período Final",
        null=True,
        blank=True,
        help_text="Data final do período do inventário.",
    )

    tipo = models.CharField(
        "Tipo",
        max_length=20,
        choices=constants.TIPOS_INVENTARIO,
    )

    unidade_administrativa = models.ForeignKey(
        UnidadeAdministrativa,
        on_delete=models.PROTECT,
        related_name="inventarios",
        verbose_name="Unidade Administrativa",
    )

    status = models.CharField(
        "Status",
        max_length=20,
        choices=constants.STATUS_INVENTARIO,
        default=constants.INVENTARIO_EM_ABERTO,
    )

    criado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name="inventarios_criados",
        verbose_name="Criado por",
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)

    fechado_por = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="inventarios_fechados",
        verbose_name="Fechado por",
    )
    fechado_em = models.DateTimeField("Fechado em", null=True, blank=True)

    class Meta:
        # ✅ Sem periodo_inicial. Unique agora:
        # - ANUAL: único por (UA, tipo, ano) => garantimos via constraint condicional
        # - EVENTUAL: único por (UA, tipo, periodo_final)
        verbose_name = "Gerenciamento de Inventário"
        verbose_name_plural = "Gerenciamento de Inventário"
        ordering = ["-criado_em", "unidade_administrativa"]

        indexes = [
            models.Index(fields=["unidade_administrativa", "tipo"]),
            models.Index(fields=["unidade_administrativa", "periodo_final"]),
        ]

        constraints = [
            # EVENTUAL: não pode repetir mesmo periodo_final na mesma UA
            models.UniqueConstraint(
                fields=["unidade_administrativa", "tipo", "periodo_final"],
                name="uniq_inventario_ua_tipo_periodo_final",
            ),
            # ANUAL: um por ano (ano calculado pelo número do inventário),
            # então garantimos pela combinação (UA, tipo, numero_inventario) já ser unique global
            # e também bloqueamos múltiplos anuais no mesmo ano usando um constraint por "numero_inventario".
            # Como numero_inventario já é unique global, isso já impede duplicar 001.XXXX/AAAA.
        ]

    def __str__(self):
        return f"{self.numero_inventario} - {self.unidade_administrativa.sigla}"

    def _get_ano_do_inventario(self):
        """
        EVENTUAL: ano vem do periodo_final
        ANUAL: ano corrente (criação/fechamento controlados por ParametroInventarioAnual)
        """
        if self.tipo == constants.INVENTARIO_EVENTUAL:
            if self.periodo_final:
                return self.periodo_final.year
            return timezone.localdate().year

        # ANUAL
        return timezone.localdate().year

    def _get_proxima_versao_eventual(self):
        ano = self._get_ano_do_inventario()

        qs = InventarioUA.objects.filter(
            unidade_administrativa=self.unidade_administrativa,
            tipo=constants.INVENTARIO_EVENTUAL,
            periodo_final__year=ano,
        )

        if self.pk:
            qs = qs.exclude(pk=self.pk)

        return qs.count() + 1

    def _validar_parametro_anual_por_data_atual(self):
        if self.tipo != constants.INVENTARIO_ANUAL:
            return

        ano = self._get_ano_do_inventario()
        hoje = timezone.localdate()

        from .models import ParametroInventarioAnual  # evita import circular, se necessário

        parametro = ParametroInventarioAnual.objects.filter(
            ano_referencia=ano,
            ativo=True,
        ).first()

        if not parametro:
            raise ValidationError(
                f"Não existe parâmetro ativo para inventário anual do ano {ano}."
            )

        if not (parametro.periodo_inicial <= hoje <= parametro.periodo_final):
            raise ValidationError(
                f"O inventário anual {ano} só pode ser criado ou fechado entre "
                f"{parametro.periodo_inicial:%d/%m/%Y} e {parametro.periodo_final:%d/%m/%Y}."
            )

    def clean(self):
        super().clean()

        if not self.tipo:
            raise ValidationError({"tipo": "Campo obrigatório."})

        # ✅ EVENTUAL exige periodo_final
        if self.tipo == constants.INVENTARIO_EVENTUAL and not self.periodo_final:
            raise ValidationError({"periodo_final": "Campo obrigatório para inventário eventual."})

        # ✅ ANUAL não usa período
        if self.tipo == constants.INVENTARIO_ANUAL:
            self.periodo_final = None

        self._validar_parametro_anual_por_data_atual()

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["numero_inventario"])

        if not self.numero_inventario:
            if not self.unidade_administrativa_id:
                raise ValidationError(
                    {"unidade_administrativa": "Unidade Administrativa é obrigatória."}
                )

            codigo = self.unidade_administrativa.codigo.replace(".", "")[-4:]
            ano = self._get_ano_do_inventario()

            if self.tipo == constants.INVENTARIO_EVENTUAL:
                versao = self._get_proxima_versao_eventual()
                self.numero_inventario = f"001.{codigo}/{ano}/{versao:03d}"
            else:
                self.numero_inventario = f"001.{codigo}/{ano}"

        super().save(*args, **kwargs)

    def finalizar(self, usuario):
        if self.status == constants.INVENTARIO_FECHADO:
            return

        self._validar_parametro_anual_por_data_atual()

        self.status = constants.INVENTARIO_FECHADO
        self.fechado_por = usuario
        self.fechado_em = timezone.now()
        self.save(update_fields=["status", "fechado_por", "fechado_em"])

    @property
    def esta_aberto(self):
        return self.status == constants.INVENTARIO_EM_ABERTO


class ItemInventario(models.Model):

    inventario = models.ForeignKey(
        InventarioUA,
        on_delete=models.CASCADE,
        related_name="itens",
        verbose_name="Inventário",
    )

    bem = models.ForeignKey(
        BemPatrimonial,
        on_delete=models.PROTECT,
        related_name="itens_inventario",
        verbose_name="Bem Patrimonial",
    )

    situacao = models.CharField(
        "Situação",
        max_length=30,
        choices=constants.SITUACOES_ITEM_INVENTARIO,
        default=constants.ENCONTRADO_SEM_DIVERGENCIA,
        help_text="Situação do bem no momento da criação do inventário",
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
        unique_together = ("inventario", "bem")
        verbose_name = "Item de Inventário"
        verbose_name_plural = "Itens de Inventário"
        ordering = ["bem__numero_patrimonial"]

        indexes = [
            models.Index(fields=["inventario", "bem"]),
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
        return self.situacao != constants.BAIXA_FISICA


class OcorrenciaInventario(models.Model):

    item = models.ForeignKey(
        ItemInventario,
        on_delete=models.CASCADE,
        related_name="ocorrencias",
        verbose_name="Item de Inventário",
    )

    situacao = models.CharField(
        "Situação",
        max_length=30,
        choices=constants.SITUACOES_ITEM_INVENTARIO,
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
        verbose_name = "Ocorrência de Inventário"
        verbose_name_plural = "Ocorrências de Inventário"

        indexes = [
            models.Index(fields=["item", "registrado_em"]),
        ]

    def __str__(self):
        return f"{self.item.bem.numero_patrimonial} - {self.get_situacao_display()}"
