from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bem_patrimonial", "0028_fix_bempatrimonial_atualizado_em_not_null"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            UPDATE bem_patrimonial_movimentacaobempatrimonial
            SET atualizado_em = COALESCE(atualizado_em, criado_em, NOW())
            WHERE atualizado_em IS NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name="movimentacaobempatrimonial",
            name="atualizado_em",
            field=models.DateTimeField(
                auto_now=True,
                blank=True,
                verbose_name="Atualizado em",
            ),
        ),
        migrations.RunSQL(
            sql="""
            UPDATE bem_patrimonial_statusbempatrimonial
            SET atualizado_em = COALESCE(atualizado_em, NOW())
            WHERE atualizado_em IS NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name="statusbempatrimonial",
            name="atualizado_em",
            field=models.DateTimeField(
                auto_now=True,
                blank=True,
                verbose_name="Atualizado em",
            ),
        ),
    ]
