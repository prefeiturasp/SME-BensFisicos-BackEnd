from import_export import resources, fields

from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria


class UnidadeOrcamentariaResource(resources.ModelResource):

    ativa_display = fields.Field(
        column_name="Status",
        attribute="ativa",
    )

    class Meta:
        model = UnidadeOrcamentaria
        fields = (
            "codigo",
            "sigla",
            "nome",
            "orgao",
            "codigo_orgao",
            "ativa_display",
        )
        export_order = (
            "codigo",
            "sigla",
            "nome",
            "orgao",
            "codigo_orgao",
            "ativa_display",
        )

    def dehydrate_ativa_display(self, uo):
        return "Ativa" if uo.ativa else "Inativa"


class UnidadeAdministrativaResource(resources.ModelResource):

    status_display = fields.Field(
        column_name="Status",
        attribute="status",
    )

    class Meta:
        model = UnidadeAdministrativa
        fields = ("codigo", "sigla", "nome", "status_display")
        export_order = ("codigo", "sigla", "nome", "status_display")

    def dehydrate_status_display(self, ua):
        return ua.get_status_display()
