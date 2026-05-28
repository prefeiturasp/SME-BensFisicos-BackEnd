from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bem_patrimonial", "0037_alter_baixafisicabempatrimonial_criado_por_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transferenciabempatrimonial",
            name="numero_processo",
            field=models.CharField(
                max_length=64,
                unique=True,
                verbose_name="Número do processo",
            ),
        ),
    ]