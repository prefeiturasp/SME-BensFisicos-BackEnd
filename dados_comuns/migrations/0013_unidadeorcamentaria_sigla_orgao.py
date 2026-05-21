from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dados_comuns", "0012_unidadeorcamentaria_orgao_codigo_orgao"),
    ]

    operations = [
        migrations.AddField(
            model_name="unidadeorcamentaria",
            name="sigla_orgao",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Sigla do Órgão",
            ),
        ),
    ]