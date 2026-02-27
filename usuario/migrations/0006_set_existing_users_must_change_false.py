from django.db import migrations


def set_existing_users_must_change_false(apps, schema_editor):
    usuario_model = apps.get_model("usuario", "Usuario")
    # Marca todos existentes como False (cobre inclusive valores NULL se houver)
    usuario_model.objects.all().update(must_change_password=False)


def noop(apps, schema_editor):
    # Nenhuma ação ao reverter: must_change_password permanece como está.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("usuario", "0005_usuario_last_password_change"),
    ]

    operations = [
        migrations.RunPython(set_existing_users_must_change_false, reverse_code=noop),
    ]
