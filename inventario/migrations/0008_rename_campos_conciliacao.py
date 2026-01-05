from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0007_rename_inventario_para_conciliacao"),
    ]

    operations = [
        migrations.RenameField(
            model_name="conciliacaoua",
            old_name="numero_inventario",
            new_name="numero_conciliacao",
        ),
        migrations.RenameField(
            model_name="itemconciliacao",
            old_name="inventario",
            new_name="conciliacao",
        ),
    ]