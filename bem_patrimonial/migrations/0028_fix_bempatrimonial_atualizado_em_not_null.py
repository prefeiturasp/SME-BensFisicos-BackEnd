from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bem_patrimonial", "0027_bempatrimonial_observacao_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            UPDATE bem_patrimonial_bempatrimonial
            SET atualizado_em = COALESCE(atualizado_em, criado_em, NOW())
            WHERE atualizado_em IS NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name="bempatrimonial",
            name="atualizado_em",
            field=models.DateTimeField(
                auto_now=True,
                blank=True,
                verbose_name="Atualizado em",
            ),
        ),
    ]
