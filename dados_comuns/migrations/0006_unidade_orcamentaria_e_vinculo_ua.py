from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dados_comuns", "0005_historicogeral_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="UnidadeOrcamentaria",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.CharField("Código", unique=True, max_length=20, help_text="Código da Unidade Orçamentária (ex.: 01.16.10).")),
                ("nome", models.CharField("Nome", max_length=255)),
                ("ativa", models.BooleanField("Ativa", default=True)),
            ],
            options={
                "verbose_name": "Unidade Orçamentária",
                "verbose_name_plural": "Unidades Orçamentárias",
                "ordering": ["codigo"],
            },
        ),
        migrations.AddField(
            model_name="unidadeadministrativa",
            name="unidade_orcamentaria",
            field=models.ForeignKey(
                verbose_name="Unidade Orçamentária",
                to="dados_comuns.unidadeorcamentaria",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="unidades_administrativas",
                null=True,
                blank=True,
            ),
        ),
    ]