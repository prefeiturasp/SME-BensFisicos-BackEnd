# Generated by Django 4.1.3 on 2023-03-06 21:48

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='BemPatrimonial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=255, verbose_name='Nome do bem')),
                ('data_compra_entrega', models.DateField(verbose_name='Data da compra/entrega')),
                ('origem', models.PositiveIntegerField(choices=[(1, 'Repasse de verba'), (2, 'Aquisição direta'), (3, 'Transferência'), (4, 'Movimentação')], verbose_name='Origem')),
                ('marca', models.CharField(max_length=255, verbose_name='Marca')),
                ('modelo', models.CharField(max_length=255, verbose_name='Modelo')),
                ('quantidade', models.PositiveIntegerField(verbose_name='Quantidade')),
                ('descricao', models.TextField(verbose_name='Descrição')),
                ('valor_unitario', models.DecimalField(decimal_places=2, max_digits=16, verbose_name='Valor unitário')),
                ('numero_processo', models.PositiveIntegerField(verbose_name='Número do processo de incorporação/transferência')),
                ('status', models.PositiveIntegerField(choices=[(1, 'Aguardando aprovação'), (2, 'Aprovado'), (3, 'Não aprovado')], default=1, verbose_name='Status')),
                ('autorizacao_no_doc_em', models.DateField(blank=True, null=True, verbose_name='Autorização no DOC em')),
                ('numero_nibpm', models.PositiveIntegerField(blank=True, null=True, verbose_name='Número NIBPM')),
                ('numero_cimbpm', models.PositiveIntegerField(blank=True, null=True, verbose_name='Número CIMBPM')),
                ('numero_patrimonial', models.PositiveIntegerField(blank=True, null=True, verbose_name='Número Patrimonial')),
                ('localizacao', models.CharField(blank=True, max_length=255, null=True, verbose_name='Localização')),
                ('numero_serie', models.PositiveIntegerField(blank=True, null=True, verbose_name='Número de série')),
                ('criado_em', models.DateTimeField(auto_now=True, verbose_name='Criado em')),
                ('atualizado_em', models.DateTimeField(auto_now=True, null=True, verbose_name='Atualizado em')),
            ],
            options={
                'verbose_name': 'bem patrimonial',
                'verbose_name_plural': 'bens patrimoniais',
            },
        ),
        migrations.CreateModel(
            name='HistoricoStatusBemPatrimonial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.PositiveIntegerField(choices=[(1, 'Aguardando aprovação'), (2, 'Aprovado'), (3, 'Não aprovado')], default=1, verbose_name='Status')),
                ('observacao', models.TextField(blank=True, null=True, verbose_name='Observação')),
                ('atualizado_em', models.DateTimeField(auto_now=True, null=True, verbose_name='Atualizado em')),
            ],
            options={
                'verbose_name': 'histórico de status',
                'verbose_name_plural': 'histórico de status',
            },
        ),
    ]
