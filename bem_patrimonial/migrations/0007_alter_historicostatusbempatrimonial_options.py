# Generated by Django 4.1.3 on 2023-03-03 19:49

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('bem_patrimonial', '0006_alter_historicostatusbempatrimonial_options'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='historicostatusbempatrimonial',
            options={'verbose_name': 'histórico de status', 'verbose_name_plural': 'histórico de status'},
        ),
    ]