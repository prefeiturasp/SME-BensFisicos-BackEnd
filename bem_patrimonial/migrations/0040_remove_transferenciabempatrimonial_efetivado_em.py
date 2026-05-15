from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("bem_patrimonial", "0039_remove_transferenciabempatrimonial_efetivado_por"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="transferenciabempatrimonial",
            name="efetivado_em",
        ),
    ]