# Generated by Django 4.1.3 on 2023-02-14 18:39

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='UnidadeAdministrativa',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(max_length=255, verbose_name='Codigo')),
                ('sigla', models.CharField(max_length=255, verbose_name='sigla')),
                ('nome', models.CharField(max_length=255, verbose_name='nome')),
                ('created_at', models.DateTimeField(auto_now=True, verbose_name='Criado em')),
                ('updated_at', models.DateTimeField(auto_now=True, null=True, verbose_name='Atualizado em')),
            ],
            options={
                'verbose_name': 'unidade administrativa',
                'verbose_name_plural': 'unidades administrativas',
            },
        ),
    ]