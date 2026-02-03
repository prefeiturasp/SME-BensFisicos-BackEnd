from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dados_comuns", "0007_vincular_uo_padrao_em_uas"),
    ]

    operations = [
        migrations.AlterField(
            model_name="unidadeadministrativa",
            name="unidade_orcamentaria",
            field=models.ForeignKey(
                verbose_name="Unidade Orçamentária",
                to="dados_comuns.unidadeorcamentaria",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="unidades_administrativas",
                null=False,
                blank=False,
            ),
        ),
    ]