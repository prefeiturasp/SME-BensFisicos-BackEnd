from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0008_rename_campos_conciliacao"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="conciliacaoua",
            options={
                "verbose_name": "Conciliação",
                "verbose_name_plural": "Conciliações",
                "ordering": ["-created_at"],
            },
        ),
    ]