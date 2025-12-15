from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max
from django.utils import timezone

from bem_patrimonial.models import BemPatrimonial
from dados_comuns.models import UnidadeAdministrativa
from usuario.models import Usuario

from . import constants


class InventarioUA(models.Model):

    numero_inventario = models.CharField(
        "Número do Inventário",
        max_length=30,
        unique=True,
        help_text="Formato: 001.XXXX/AAAA (anual) ou 001.XXXX/AAAA/VVV (eventual)",
    )

    periodo_inicial = models.DateField(
        "Período Inicial",
        help_text="Data inicial do período do inventário",
    )
    periodo_final = models.DateField(
        "Período Final",
        help_text="Data final do período do inventário",
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
        unique_together = (
            "unidade_administrativa",
            "tipo",
            "periodo_inicial",
            "periodo_final",
        )
        verbose_name = "Gerenciamento de Inventário"
        verbose_name_plural = "Gerenciamento de Inventário"
        ordering = ["-periodo_inicial", "unidade_administrativa", "-criado_em"]

        indexes = [
            models.Index(fields=["unidade_administrativa", "periodo_inicial"]),
            models.Index(fields=["unidade_administrativa", "tipo", "periodo_inicial"]),
        ]

    def __str__(self):
        return f"{self.numero_inventario} - {self.unidade_administrativa.sigla}"

    def clean(self):
        super().clean()

        if not self.tipo:
            raise ValidationError({"tipo": "Campo obrigatório."})

        if self.periodo_inicial and self.periodo_final:
            if self.periodo_inicial > self.periodo_final:
                raise ValidationError(
                    {
                        "periodo_final": "O Período Final deve ser maior ou igual ao Período Inicial."
                    }
                )

            if self.periodo_inicial.year != self.periodo_final.year:
                raise ValidationError(
                    {
                        "periodo_final": "O período do inventário deve estar dentro do mesmo ano."
                    }
                )

    def _get_ano_do_inventario(self):
        if not self.periodo_inicial:
            return timezone.now().year
        return self.periodo_inicial.year

    def _get_proxima_versao_eventual(self):
        """
        Versão = quantidade de inventários EVENTUAIS existentes para a mesma UA no mesmo ano + 1.
        Ex.: existem 10 eventuais -> próximo = 11 (gravado como 011 no número).
        """
        ano = self._get_ano_do_inventario()

        qs = InventarioUA.objects.filter(
            unidade_administrativa=self.unidade_administrativa,
            tipo=constants.INVENTARIO_EVENTUAL,
            periodo_inicial__year=ano,
        )

        if self.pk:
            qs = qs.exclude(pk=self.pk)

        total = qs.count()
        return total + 1

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
