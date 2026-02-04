from django.db import migrations, models
from django.db.models import Q


UO_CODIGO_PADRAO = "01.16.10"


def preencher_uo_padrao(apps, schema_editor):
    ParametroConciliacaoAnual = apps.get_model(
        "inventario", "ParametroConciliacaoAnual"
    )
    UnidadeOrcamentaria = apps.get_model("dados_comuns", "UnidadeOrcamentaria")

    try:
        uo = UnidadeOrcamentaria.objects.get(codigo=UO_CODIGO_PADRAO)
    except UnidadeOrcamentaria.DoesNotExist:
        raise RuntimeError(
            f"Não foi encontrada UnidadeOrcamentaria com codigo={UO_CODIGO_PADRAO}. "
            "Crie essa UO antes de aplicar esta migration."
        )

    ParametroConciliacaoAnual.objects.filter(unidade_orcamentaria__isnull=True).update(
        unidade_orcamentaria=uo
    )


def reverter_preenchimento_uo(apps, schema_editor):

    ParametroConciliacaoAnual = apps.get_model(
        "inventario", "ParametroConciliacaoAnual"
    )
    ParametroConciliacaoAnual.objects.update(unidade_orcamentaria=None)


class Migration(migrations.Migration):

    dependencies = [
        ("inventario", "0017_recalcular_bloqueio_apenas_em_processo"),
        ("dados_comuns", "0008_tornar_uo_obrigatoria_em_ua"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="parametroconciliacaoanual",
            name="unique_parametro_conciliacao_anual_ativo_por_ano",
        ),
        migrations.AddField(
            model_name="parametroconciliacaoanual",
            name="unidade_orcamentaria",
            field=models.ForeignKey(
                to="dados_comuns.unidadeorcamentaria",
                on_delete=models.PROTECT,
                related_name="parametros_conciliacao_anual",
                verbose_name="Unidade Orçamentária",
                null=True,
                blank=True,
            ),
        ),
        migrations.RunPython(preencher_uo_padrao, reverter_preenchimento_uo),
        migrations.AlterField(
            model_name="parametroconciliacaoanual",
            name="unidade_orcamentaria",
            field=models.ForeignKey(
                to="dados_comuns.unidadeorcamentaria",
                on_delete=models.PROTECT,
                related_name="parametros_conciliacao_anual",
                verbose_name="Unidade Orçamentária",
                null=False,
                blank=False,
            ),
        ),
        migrations.AddConstraint(
            model_name="parametroconciliacaoanual",
            constraint=models.UniqueConstraint(
                fields=["unidade_orcamentaria", "ano_referencia"],
                condition=Q(ativo=True),
                name="unique_parametro_conciliacao_anual_ativo_por_uo_ano",
            ),
        ),
    ]
