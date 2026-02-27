from django.db import migrations


def populate_m2m(apps, schema_editor):
    Usuario = apps.get_model("usuario", "Usuario")
    for user in Usuario.objects.filter(unidade_administrativa__isnull=False):
        user.unidades_administrativas.add(user.unidade_administrativa)


def reverse_populate(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("usuario", "0009_usuario_unidades_administrativas")]
    operations = [migrations.RunPython(populate_m2m, reverse_populate)]
