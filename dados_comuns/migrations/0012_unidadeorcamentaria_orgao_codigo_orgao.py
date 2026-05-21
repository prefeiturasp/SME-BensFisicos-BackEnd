from django.core.validators import RegexValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dados_comuns", "0011_remove_legacy_agendamento_suporte"),
    ]

    operations = [
        migrations.AddField(
            model_name="unidadeorcamentaria",
            name="codigo_orgao",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Informe no padrão NN.NN.",
                max_length=5,
                validators=[
                    RegexValidator(
                        message="Código do Órgão deve seguir o padrão NN.NN.",
                        regex="^\\d{2}\\.\\d{2}$",
                    )
                ],
                verbose_name="Código do Órgão",
            ),
        ),
        migrations.AddField(
            model_name="unidadeorcamentaria",
            name="orgao",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Órgão",
            ),
        ),
    ]