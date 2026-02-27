from django.db import migrations


CODIGO_UO_PADRAO = "01.16.10"
NOME_UO_PADRAO = "SECRETARIA MUNICIPAL DE EDUCAÇÃO"


def criar_uo_padrao_e_vincular_uas(apps, schema_editor):
    unidade_orcamentaria_model = apps.get_model("dados_comuns", "UnidadeOrcamentaria")
    unidade_administrativa_model = apps.get_model("dados_comuns", "UnidadeAdministrativa")

    uo, _ = unidade_orcamentaria_model.objects.get_or_create(
        codigo=CODIGO_UO_PADRAO,
        defaults={
            "nome": NOME_UO_PADRAO,
            "ativa": True,
        },
    )

    unidade_administrativa_model.objects.filter(unidade_orcamentaria__isnull=True).update(
        unidade_orcamentaria=uo
    )


def reverter(apps, schema_editor):
    # Nenhuma ação necessária ao reverter: UAs continuam com a UO que tinham.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("dados_comuns", "0006_unidade_orcamentaria_e_vinculo_ua"),
    ]

    operations = [
        migrations.RunPython(criar_uo_padrao_e_vincular_uas, reverter),
    ]