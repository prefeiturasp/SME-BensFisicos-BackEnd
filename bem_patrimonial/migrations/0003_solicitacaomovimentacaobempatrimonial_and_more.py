# Generated by Django 4.1.3 on 2023-03-09 19:47

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dados_comuns', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('bem_patrimonial', '0002_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SolicitacaoMovimentacaoBemPatrimonial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.PositiveIntegerField(choices=[(1, 'Enviada'), (2, 'Aceita'), (3, 'Rejeitada')], default=1, verbose_name='Status')),
                ('observacao', models.TextField(blank=True, null=True, verbose_name='Observacao')),
                ('criado_em', models.DateTimeField(auto_now=True, verbose_name='Criado em')),
                ('atualizado_em', models.DateTimeField(auto_now=True, null=True, verbose_name='Atualizado em')),
                ('aprovado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_aprovadopor', to=settings.AUTH_USER_MODEL, verbose_name='Aprovado por')),
                ('bem_patrimonial', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bem_patrimonial.bempatrimonial', verbose_name='Bem patrimonial')),
                ('rejeitado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(class)s_rejeitadopor', to=settings.AUTH_USER_MODEL, verbose_name='Rejeitado por')),
                ('solicitado_por', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, related_name='%(class)s_solicitadopor', to=settings.AUTH_USER_MODEL, verbose_name='Solicitado por')),
                ('unidade_administrativa_destino', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dados_comuns.unidadeadministrativa', verbose_name='Unidade administrativa destino')),
            ],
            options={
                'verbose_name': 'solicitação de movimentação de bem patrimonial',
                'verbose_name_plural': 'solicitações de movimentação de bem patrimonial',
            },
        ),
        migrations.CreateModel(
            name='HistoricoMovimentacaoBemPatrimonial',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('criado_em', models.DateTimeField(auto_now=True, verbose_name='Criado em')),
                ('atualizado_em', models.DateTimeField(auto_now=True, null=True, verbose_name='Atualizado em')),
                ('bem_patrimonial', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='bem_patrimonial.bempatrimonial', verbose_name='Bem patrimonial')),
                ('solicitacao_movimentacao', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='bem_patrimonial.solicitacaomovimentacaobempatrimonial', verbose_name='Solicitação de movimentação')),
                ('unidade_administrativa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='dados_comuns.unidadeadministrativa', verbose_name='Unidade administrativa')),
            ],
            options={
                'verbose_name': 'histórico de movimentação de bem patrimonial',
                'verbose_name_plural': 'históricos de movimentação de bem patrimonial',
            },
        ),
    ]
