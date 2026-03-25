import re

from rest_framework import serializers

from dados_comuns.models import UnidadeAdministrativa


class UnidadeAdministrativaListSerializer(serializers.ModelSerializer):
    unidade_orcamentaria_codigo = serializers.CharField(
        source="unidade_orcamentaria.codigo", read_only=True
    )
    unidade_orcamentaria_nome = serializers.CharField(
        source="unidade_orcamentaria.nome", read_only=True
    )
    unidade_orcamentaria_sigla = serializers.CharField(
        source="unidade_orcamentaria.sigla", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = UnidadeAdministrativa
        fields = [
            "id",
            "codigo",
            "sigla",
            "nome",
            "status",
            "status_display",
            "unidade_orcamentaria",
            "unidade_orcamentaria_codigo",
            "unidade_orcamentaria_nome",
            "unidade_orcamentaria_sigla",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class UnidadeAdministrativaDetailSerializer(UnidadeAdministrativaListSerializer):
    CODIGO_SUFIXO_RE = re.compile(r"^\d{3,4}$")

    class Meta(UnidadeAdministrativaListSerializer.Meta):
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "codigo": {
                "help_text": "Informe o sufixo numérico com 3 ou 4 dígitos (ex.: 002 ou 1002). O sistema compõe automaticamente o código completo com o prefixo da Unidade Orçamentária."
            }
        }

    def _extrair_sufixo_codigo(self, codigo, codigo_uo):
        codigo = (codigo or "").strip()

        if self.CODIGO_SUFIXO_RE.fullmatch(codigo):
            return codigo

        prefixo = f"{codigo_uo}."
        if codigo.startswith(prefixo):
            candidato = codigo[len(prefixo) :]
            if self.CODIGO_SUFIXO_RE.fullmatch(candidato):
                return candidato

        return None

    def _validar_codigo_unico(self, codigo):
        queryset = UnidadeAdministrativa.objects.filter(codigo=codigo)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)

        if queryset.exists():
            raise serializers.ValidationError(
                {"codigo": "Já existe uma unidade administrativa com este código."}
            )

    def validate(self, attrs):
        uo = attrs.get("unidade_orcamentaria")
        if self.instance and uo is None:
            uo = self.instance.unidade_orcamentaria

        if uo is None:
            return attrs

        codigo_informado = attrs.get("codigo")

        if self.instance and codigo_informado is None:
            if "unidade_orcamentaria" in attrs:
                sufixo = self._extrair_sufixo_codigo(
                    self.instance.codigo,
                    self.instance.unidade_orcamentaria.codigo,
                )
                if not sufixo:
                    raise serializers.ValidationError(
                        {
                            "codigo": "Ao alterar a Unidade Orçamentária, informe o código com 3 ou 4 dígitos numéricos."
                        }
                    )
                attrs["codigo"] = f"{uo.codigo}.{sufixo}"
                self._validar_codigo_unico(attrs["codigo"])
            return attrs

        if codigo_informado is None:
            raise serializers.ValidationError(
                {
                    "codigo": "Informe o código da unidade administrativa com 3 ou 4 dígitos numéricos."
                }
            )

        sufixo = self._extrair_sufixo_codigo(str(codigo_informado), uo.codigo)
        if not sufixo:
            raise serializers.ValidationError(
                {
                    "codigo": "Código inválido. Informe 3 ou 4 dígitos numéricos (ex.: 002 ou 1002)."
                }
            )

        attrs["codigo"] = f"{uo.codigo}.{sufixo}"
        self._validar_codigo_unico(attrs["codigo"])
        return attrs


class UnidadeAdministrativaExportSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = UnidadeAdministrativa
        fields = ["codigo", "sigla", "nome", "status_display"]


class UnidadeAdministrativaHistoricoAcaoSerializer(serializers.Serializer):
    campo = serializers.CharField()
    valor_antigo = serializers.CharField(allow_null=True)
    valor_novo = serializers.CharField(allow_null=True)


class UnidadeAdministrativaHistoricoGrupoSerializer(serializers.Serializer):
    alterado_em = serializers.DateTimeField()
    alterado_por = serializers.IntegerField(allow_null=True)
    alterado_por_nome = serializers.CharField(allow_null=True)
    acoes = UnidadeAdministrativaHistoricoAcaoSerializer(many=True)


class UnidadeAdministrativaExportQuerySerializer(serializers.Serializer):
    formato = serializers.ChoiceField(choices=["csv", "xls", "xlsx", "pdf"])
