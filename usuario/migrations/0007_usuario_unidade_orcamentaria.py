from django.db import migrations, models
import django.db.models.deletion


def preencher_uo_no_usuario_a_partir_da_ua(apps, schema_editor):
    usuario_model = apps.get_model("usuario", "Usuario")

    for usuario in usuario_model.objects.select_related(
        "unidade_administrativa__unidade_orcamentaria"
    ).all():
        if usuario.unidade_orcamentaria_id:
            continue
        if (
            usuario.unidade_administrativa_id
            and usuario.unidade_administrativa.unidade_orcamentaria_id
        ):
            usuario.unidade_orcamentaria = (
                usuario.unidade_administrativa.unidade_orcamentaria
            )
            usuario.save(update_fields=["unidade_orcamentaria"])


def reverter(apps, schema_editor):
    # Não desfaz preenchimento de unidade_orcamentaria nos usuários.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("usuario", "0006_set_existing_users_must_change_false"),
        ("dados_comuns", "0008_tornar_uo_obrigatoria_em_ua"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="unidade_orcamentaria",
            field=models.ForeignKey(
                verbose_name="Unidade Orçamentária",
                to="dados_comuns.unidadeorcamentaria",
                on_delete=django.db.models.deletion.SET_NULL,
                null=True,
                blank=True,
                related_name="usuarios",
            ),
        ),
        migrations.RunPython(preencher_uo_no_usuario_a_partir_da_ua, reverter),
    ]
