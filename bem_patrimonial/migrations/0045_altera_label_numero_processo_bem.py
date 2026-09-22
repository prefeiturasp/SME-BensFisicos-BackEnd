from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bem_patrimonial", "0044_unificar_nbbpm_ua_ano"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bempatrimonial",
            name="numero_processo",
            field=models.CharField(
                blank=True,
                null=True,
                default="",
                max_length=64,
                verbose_name="Número do processo",
            ),
        ),
    ]
