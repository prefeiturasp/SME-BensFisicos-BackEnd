from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("bem_patrimonial", "0036_transferenciabempatrimonial_numero_ntbpm"),
    ]

    operations = [
        migrations.AlterField(
            model_name="baixafisicabempatrimonial",
            name="criado_por",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="baixas_fisicas_criadas",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Usuário que solicitou a baixa",
            ),
        ),
        migrations.AlterField(
            model_name="baixafisicabempatrimonial",
            name="data_aprovacao",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Data da aprovação",
            ),
        ),
        migrations.AlterField(
            model_name="baixafisicabempatrimonial",
            name="data_criacao",
            field=models.DateTimeField(
                auto_now_add=True,
                verbose_name="Data da solicitação",
            ),
        ),
    ]