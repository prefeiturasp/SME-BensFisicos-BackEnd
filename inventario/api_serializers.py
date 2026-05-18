from rest_framework import serializers

from inventario.models import ParametroConciliacaoAnual


class ParametroConciliacaoAnualListSerializer(serializers.ModelSerializer):
    unidade_orcamentaria_codigo = serializers.CharField(
        source="unidade_orcamentaria.codigo",
        read_only=True,
    )
    unidade_orcamentaria_nome = serializers.CharField(
        source="unidade_orcamentaria.nome",
        read_only=True,
    )
    unidade_orcamentaria_sigla = serializers.CharField(
        source="unidade_orcamentaria.sigla",
        read_only=True,
    )
    esta_vigente = serializers.BooleanField(read_only=True)

    class Meta:
        model = ParametroConciliacaoAnual
        fields = [
            "id",
            "unidade_orcamentaria",
            "unidade_orcamentaria_codigo",
            "unidade_orcamentaria_nome",
            "unidade_orcamentaria_sigla",
            "ano_referencia",
            "periodo_inicial",
            "periodo_final",
            "ativo",
            "esta_vigente",
        ]
        read_only_fields = fields


class ParametroConciliacaoAnualDetailSerializer(
    ParametroConciliacaoAnualListSerializer
):
    class Meta(ParametroConciliacaoAnualListSerializer.Meta):
        read_only_fields = ["id", "esta_vigente"]
