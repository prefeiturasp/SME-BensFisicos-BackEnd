from django.db import migrations


def cria_itens_movimentacao(apps, schema_editor):
    Movimentacao = apps.get_model(
        "bem_patrimonial", "MovimentacaoBemPatrimonial"
    )
    MovimentacaoBensItem = apps.get_model(
        "bem_patrimonial", "MovimentacaoBensItem"
    )

    db_alias = schema_editor.connection.alias

    # Só movimentações que ainda têm bem_patrimonial associado
    movimentacoes = Movimentacao.objects.using(db_alias).filter(
        bem_patrimonial__isnull=False
    )

    itens_para_criar = []

    for mov in movimentacoes:
        bem_id = mov.bem_patrimonial_id
        mov_id = mov.id

        # Garante que não duplica se já existir item
        existe = MovimentacaoBensItem.objects.using(db_alias).filter(
            movimentacao_id=mov_id,
            bem_id=bem_id,
        ).exists()

        if not existe:
            itens_para_criar.append(
                MovimentacaoBensItem(
                    movimentacao_id=mov_id,
                    bem_id=bem_id,
                )
            )

    if itens_para_criar:
        # bulk_create não dispara signals
        MovimentacaoBensItem.objects.using(db_alias).bulk_create(
            itens_para_criar,
            ignore_conflicts=True,  # segurança extra se já houver algum
        )


class Migration(migrations.Migration):

    dependencies = [
        ("bem_patrimonial", "0013_movimentacaobempatrimonial_bens_and_more"),
    ]

    operations = [
        migrations.RunPython(
            cria_itens_movimentacao,
            migrations.RunPython.noop,  # reverso não faz nada
        ),
    ]
