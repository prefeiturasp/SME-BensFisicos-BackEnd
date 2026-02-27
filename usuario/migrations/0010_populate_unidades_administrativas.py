from django.db import migrations


def populate_m2m(apps, schema_editor):
    usuario_model = apps.get_model("usuario", "Usuario")
    for user in usuario_model.objects.filter(unidade_administrativa__isnull=False):
        user.unidades_administrativas.add(user.unidade_administrativa)


def reverse_populate(apps, schema_editor):
    # Reversão intencionalmente vazia: desfazer o populate exigiria limpar M2M por usuário.
    pass


class Migration(migrations.Migration):
    dependencies = [("usuario", "0009_usuario_unidades_administrativas")]
    operations = [migrations.RunPython(populate_m2m, reverse_populate)]
