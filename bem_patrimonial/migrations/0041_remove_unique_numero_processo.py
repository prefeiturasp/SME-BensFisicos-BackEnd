from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bem_patrimonial", "0040_remove_transferenciabempatrimonial_efetivado_em"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transferenciabempatrimonial",
            name="numero_ntbpm",
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=30,
                null=True,
                unique=True,
                verbose_name="Número NTBPM",
            ),
        ),
        migrations.AlterField(
            model_name="transferenciabempatrimonial",
            name="numero_processo",
            field=models.CharField(
                max_length=64,
                unique=False,
                verbose_name="Número do processo",
            ),
        ),
    ]
