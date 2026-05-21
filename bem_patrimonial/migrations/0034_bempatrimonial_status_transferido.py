from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("bem_patrimonial", "0033_alter_bempatrimonial_localizacao_numero_processo_nullable"),
    ]

    operations = [
        migrations.AlterField(
            model_name="bempatrimonial",
            name="status",
            field=models.CharField(
                choices=[
                    ("aguardando_aprovacao", "Aguardando aprovação"),
                    ("aprovado", "Aprovado"),
                    ("nao_aprovado", "Não aprovado"),
                    ("bloqueado", "Bloqueado para movimentação"),
                    (
                        "baixa_fisica_aguardando_aprovacao",
                        "Baixa Física - Aguardando aprovação",
                    ),
                    ("baixa_fisica", "Baixa Física"),
                    ("transferido", "Transferido"),
                ],
                default="aguardando_aprovacao",
                max_length=50,
                verbose_name="Status",
            ),
        ),
        migrations.AlterField(
            model_name="statusbempatrimonial",
            name="status",
            field=models.CharField(
                choices=[
                    ("aguardando_aprovacao", "Aguardando aprovação"),
                    ("aprovado", "Aprovado"),
                    ("nao_aprovado", "Não aprovado"),
                    ("bloqueado", "Bloqueado para movimentação"),
                    (
                        "baixa_fisica_aguardando_aprovacao",
                        "Baixa Física - Aguardando aprovação",
                    ),
                    ("baixa_fisica", "Baixa Física"),
                    ("transferido", "Transferido"),
                ],
                default="aguardando_aprovacao",
                max_length=50,
                verbose_name="Status",
            ),
        ),
    ]