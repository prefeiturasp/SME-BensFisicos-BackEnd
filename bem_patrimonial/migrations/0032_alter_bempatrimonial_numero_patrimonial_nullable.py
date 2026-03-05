from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bem_patrimonial", "0031_remove_bempatrimonial_uniq_numero_patrimonial_ativo_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bempatrimonial",
            name="numero_patrimonial",
            field=models.CharField(
                blank=True,
                null=True,
                db_index=True,
                default="",
                help_text="Formato padrão: 000.000000000-0",
                max_length=20,
                verbose_name="Número Patrimonial",
            ),
        ),
    ]
