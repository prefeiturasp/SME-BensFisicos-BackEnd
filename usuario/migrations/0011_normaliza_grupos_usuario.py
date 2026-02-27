from django.db import migrations


GRUPO_GESTOR_PATRIMONIO = "GESTOR_PATRIMONIO"
GRUPO_OPERADOR_INVENTARIO = "OPERADOR_INVENTARIO"


def normaliza_grupos_usuario(apps, schema_editor):
    usuario_model = apps.get_model("usuario", "Usuario")
    group_model = apps.get_model("auth", "Group")

    gestor = group_model.objects.filter(name=GRUPO_GESTOR_PATRIMONIO).first()
    operador = group_model.objects.filter(name=GRUPO_OPERADOR_INVENTARIO).first()

    if not gestor and not operador:
        return

    for usuario in usuario_model.objects.prefetch_related("groups").all().iterator():
        nomes_grupos = {g.name for g in usuario.groups.all()}

        if not nomes_grupos:
            continue

        if (
            GRUPO_GESTOR_PATRIMONIO in nomes_grupos
            and GRUPO_OPERADOR_INVENTARIO in nomes_grupos
            and gestor
        ):
            usuario.groups.set([gestor])
            continue

        if GRUPO_GESTOR_PATRIMONIO in nomes_grupos and gestor:
            usuario.groups.set([gestor])
            continue

        if GRUPO_OPERADOR_INVENTARIO in nomes_grupos and operador:
            usuario.groups.set([operador])


def reverse_noop(apps, schema_editor):
    # Reversão intencionalmente vazia: normalização de grupos não é reversível.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("usuario", "0010_populate_unidades_administrativas"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(normaliza_grupos_usuario, reverse_noop),
    ]
