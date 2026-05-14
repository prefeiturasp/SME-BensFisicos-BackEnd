from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bem_patrimonial", "0035_transferenciabempatrimonial_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="transferenciabempatrimonial",
            name="numero_ntbpm",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                max_length=30,
                unique=True,
                verbose_name="Número NTBPM",
            ),
        ),
    ]