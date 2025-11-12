# Gerado manual para corrigir unidades administrativas incorretas
# com base na última movimentação aprovada de cada bem patrimonial.

from django.db import migrations

SQL_CORRIGE_UNIDADE_POR_MOVIMENTACAO = r"""
WITH ultima_movimentacao AS (
    SELECT DISTINCT ON (bem_patrimonial_id)
        bem_patrimonial_id,
        unidade_administrativa_destino_id
    FROM bem_patrimonial_movimentacaobempatrimonial
    WHERE aprovado_por_id IS NOT NULL
    ORDER BY bem_patrimonial_id, atualizado_em DESC NULLS LAST, id DESC
)
UPDATE bem_patrimonial_bempatrimonial AS b
SET unidade_administrativa_id = m.unidade_administrativa_destino_id
FROM ultima_movimentacao AS m
WHERE b.id = m.bem_patrimonial_id
  AND b.unidade_administrativa_id IS DISTINCT FROM m.unidade_administrativa_destino_id;
"""


class Migration(migrations.Migration):

    dependencies = [
        (
            "bem_patrimonial",
            "0009_alter_bempatrimonial_numero_processo",
        ),
    ]

    operations = [
        migrations.RunSQL(
            sql=SQL_CORRIGE_UNIDADE_POR_MOVIMENTACAO,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
