from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
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
    ano_referencia = models.PositiveSmallIntegerField(
        "Ano de Referência", help_text="Ano ao qual o inventário se refere"
    )
    tipo = models.CharField(
        "Tipo",
        max_length=20,
        choices=constants.TIPOS_INVENTARIO,
        default=constants.INVENTARIO_ANUAL,
    )
    versao = models.PositiveSmallIntegerField(
        "Versão",
        default=1,
        help_text="Versão do inventário (usado apenas para inventários eventuais)",
    )
    vigencia = models.DateField(
        "Vigência",
        help_text="Data limite para finalização (padrão: 31/12/ano_referencia)",
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
        unique_together = ("unidade_administrativa", "ano_referencia", "tipo", "versao")
        verbose_name = "Gerenciamento de Inventário"
        verbose_name_plural = "Gerenciamento de Inventário"
        ordering = ["-ano_referencia", "unidade_administrativa", "-versao"]

    def __str__(self):
        return f"{self.numero_inventario} - {self.unidade_administrativa.sigla}"

    def save(self, *args, **kwargs):
        if not self.numero_inventario:
            codigo = self.unidade_administrativa.codigo.replace(".", "")[-4:]

            if self.tipo == constants.INVENTARIO_EVENTUAL:
                if not self.versao or self.versao == 1:
                    ultima_versao = (
                        InventarioUA.objects.filter(
                            unidade_administrativa=self.unidade_administrativa,
                            ano_referencia=self.ano_referencia,
                            tipo=constants.INVENTARIO_EVENTUAL,
                        ).aggregate(models.Max("versao"))["versao__max"]
                        or 0
                    )
                    self.versao = ultima_versao + 1

                self.numero_inventario = (
                    f"001.{codigo}/{self.ano_referencia}/{self.versao:03d}"
                )
            else:
                self.versao = 1  # Anual sempre versão 1
                self.numero_inventario = f"001.{codigo}/{self.ano_referencia}"

        if not self.vigencia:
            self.vigencia = date(self.ano_referencia, 12, 31)

        super().save(*args, **kwargs)

    def finalizar(self, usuario):
        self.status = constants.INVENTARIO_FECHADO
        self.fechado_por = usuario
        self.fechado_em = timezone.now()
        self.save()

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
    )
    situacao_anterior = models.CharField(
        "Situação Anterior",
        max_length=30,
        choices=constants.SITUACOES_ITEM_INVENTARIO,
        null=True,
        blank=True,
        help_text="Situação no inventário do ano anterior",
    )
    observacao = models.TextField(
        "Observação", blank=True, help_text="Observações sobre o item (opcional)"
    )
    divergencia = models.TextField(
        "Divergência",
        blank=True,
        help_text="Descrição da divergência encontrada (obrigatório quando situação = Divergente)",
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

    def __str__(self):
        return f"{self.bem.numero_patrimonial} - {self.get_situacao_display()}"

    def clean(self):
        if self.situacao == constants.DIVERGENTE and not self.divergencia:
            raise ValidationError(
                {"divergencia": "Campo obrigatório quando situação é Divergente"}
            )

    @property
    def pode_marcar_como_encontrado(self):
        return self.situacao_anterior == constants.NAO_ENCONTRADO

    @property
    def tem_ocorrencia(self):
        return self.situacao != constants.ENCONTRADO_SEM_DIVERGENCIA


class OcorrenciaInventario(models.Model):

    item = models.ForeignKey(
        ItemInventario,
        on_delete=models.CASCADE,
        related_name="ocorrencias",
        verbose_name="Item de Inventário",
    )
    situacao_anterior = models.CharField(
        "Situação Anterior", max_length=30, help_text="Situação antes da mudança"
    )
    situacao_nova = models.CharField(
        "Situação Nova", max_length=30, help_text="Nova situação após mudança"
    )
    observacao = models.TextField("Observação", blank=True)
    divergencia = models.TextField("Divergência", blank=True)
    registrado_por = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, verbose_name="Registrado por"
    )
    registrado_em = models.DateTimeField("Registrado em", auto_now_add=True)

    class Meta:
        ordering = ["-registrado_em"]
        verbose_name = "Ocorrência de Inventário"
        verbose_name_plural = "Ocorrências de Inventário"

    def __str__(self):
        return f"{self.item.bem.numero_patrimonial} - {self.situacao_anterior} → {self.situacao_nova}"
