from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("bem_patrimonial", "0038_alter_transferenciabempatrimonial_numero_processo"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="transferenciabempatrimonial",
            name="efetivado_por",
        ),
    ]