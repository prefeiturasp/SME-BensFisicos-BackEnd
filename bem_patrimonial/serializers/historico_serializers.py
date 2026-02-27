from rest_framework import serializers


class HistoricoAcaoSerializer(serializers.Serializer):
    campo = serializers.CharField()
    valor_antigo = serializers.CharField(allow_null=True)
    valor_novo = serializers.CharField(allow_null=True)


class HistoricoGrupoSerializer(serializers.Serializer):
    alterado_em = serializers.DateTimeField()
    alterado_por = serializers.IntegerField(allow_null=True)
    alterado_por_nome = serializers.CharField(allow_null=True)
    acoes = HistoricoAcaoSerializer(many=True)