from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
          ('inventario', '0006_alter_parametroinventarioanual_options'),
    ]

    operations = [
        migrations.RenameModel(
            old_name="ParametroInventarioAnual",
            new_name="ParametroConciliacaoAnual",
        ),
        migrations.RenameModel(
            old_name="InventarioUA",
            new_name="ConciliacaoUA",
        ),
        migrations.RenameModel(
            old_name="ItemInventario",
            new_name="ItemConciliacao",
        ),
        migrations.RenameModel(
            old_name="OcorrenciaInventario",
            new_name="OcorrenciaConciliacao",
        ),
    ]