from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bem_patrimonial", "0029_fix_mov_status_atualizado_em_not_null"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            UPDATE bem_patrimonial_movimentacaobempatrimonial
            SET observacao = ''
            WHERE observacao IS NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name="movimentacaobempatrimonial",
            name="observacao",
            field=models.TextField(blank=True, verbose_name="Observacao"),
        ),
        migrations.RunSQL(
            sql="""
            UPDATE bem_patrimonial_statusbempatrimonial
            SET observacao = ''
            WHERE observacao IS NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name="statusbempatrimonial",
            name="observacao",
            field=models.TextField(blank=True, verbose_name="Observação"),
        ),
    ]
