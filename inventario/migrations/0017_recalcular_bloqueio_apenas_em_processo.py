from django.db import migrations
from django.db.models import Exists, OuterRef


def recalcular_bloqueio_apenas_em_processo(apps, schema_editor):
    BemPatrimonial = apps.get_model("bem_patrimonial", "BemPatrimonial")
    ItemConciliacao = apps.get_model("inventario", "ItemConciliacao")

    # Evita depender de managers custom (soft delete etc.)
    bem_qs = BemPatrimonial._base_manager.all()

    itens_em_processo = ItemConciliacao.objects.filter(
        bem_id=OuterRef("pk"),
        situacao="EM_PROCESSO_BAIXA_FISICA",
        conciliacao__status="CONCILIACAO_EM_ABERTO",
    )

    bem_qs.update(
        bloqueado_conciliacao=Exists(itens_em_processo)
    )


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0016_alter_itemconciliacao_situacao_and_more"),
    ]

    operations = [
        migrations.RunPython(
            recalcular_bloqueio_apenas_em_processo,
            reverse_code=recalcular_bloqueio_apenas_em_processo,
        ),
    ]