from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "bem_patrimonial",
            "0032_alter_bempatrimonial_numero_patrimonial_nullable",
        ),
    ]

    operations = [
        migrations.AlterField(
            model_name="bempatrimonial",
            name="localizacao",
            field=models.CharField(
                blank=True,
                null=True,
                default="",
                max_length=255,
                verbose_name="Localização",
            ),
        ),
        migrations.AlterField(
            model_name="bempatrimonial",
            name="numero_processo",
            field=models.CharField(
                blank=True,
                null=True,
                default="",
                max_length=64,
                verbose_name="Número do processo de incorporação",
            ),
        ),
    ]
