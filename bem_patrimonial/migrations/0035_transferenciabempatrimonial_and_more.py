from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("bem_patrimonial", "0034_bempatrimonial_status_transferido"),
        ("dados_comuns", "0012_unidadeorcamentaria_orgao_codigo_orgao"),
        ("usuario", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="TransferenciaBemPatrimonial",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "numero_processo",
                    models.CharField(max_length=64, verbose_name="Número do processo"),
                ),
                (
                    "observacao",
                    models.TextField(blank=True, verbose_name="Observação"),
                ),
                ("criado_em", models.DateTimeField(auto_now_add=True, verbose_name="Criado em")),
                (
                    "atualizado_em",
                    models.DateTimeField(auto_now=True, verbose_name="Atualizado em"),
                ),
                (
                    "efetivado_em",
                    models.DateTimeField(blank=True, null=True, verbose_name="Efetivado em"),
                ),
                (
                    "criado_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transferencias_criadas",
                        to="usuario.usuario",
                        verbose_name="Criado por",
                    ),
                ),
                (
                    "efetivado_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="transferencias_efetivadas",
                        to="usuario.usuario",
                        verbose_name="Efetivado por",
                    ),
                ),
                (
                    "unidade_administrativa_destino",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transferencias_recebidas",
                        to="dados_comuns.unidadeadministrativa",
                        verbose_name="Unidade administrativa de destino",
                    ),
                ),
                (
                    "unidade_orcamentaria_destino",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transferencias_destino",
                        to="dados_comuns.unidadeorcamentaria",
                        verbose_name="Unidade orçamentária de destino",
                    ),
                ),
                (
                    "unidade_orcamentaria_origem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="transferencias_origem",
                        to="dados_comuns.unidadeorcamentaria",
                        verbose_name="Unidade orçamentária de origem",
                    ),
                ),
            ],
            options={
                "verbose_name": "transferência de bem patrimonial",
                "verbose_name_plural": "transferências de bens patrimoniais",
            },
        ),
        migrations.CreateModel(
            name="TransferenciaBensItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "bem",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transferencias_itens",
                        to="bem_patrimonial.bempatrimonial",
                    ),
                ),
                (
                    "transferencia",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="itens",
                        to="bem_patrimonial.transferenciabempatrimonial",
                    ),
                ),
            ],
            options={
                "verbose_name": "item de transferência",
                "verbose_name_plural": "itens de transferência",
            },
        ),
        migrations.AddField(
            model_name="transferenciabempatrimonial",
            name="bens",
            field=models.ManyToManyField(
                blank=True,
                related_name="transferencias",
                through="bem_patrimonial.TransferenciaBensItem",
                to="bem_patrimonial.bempatrimonial",
                verbose_name="Bens patrimoniais",
            ),
        ),
        migrations.AddConstraint(
            model_name="transferenciabensitem",
            constraint=models.UniqueConstraint(
                fields=("transferencia", "bem"),
                name="uniq_item_por_transferencia_bem",
            ),
        ),
    ]