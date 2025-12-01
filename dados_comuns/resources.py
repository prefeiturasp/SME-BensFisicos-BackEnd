from import_export import resources, fields
from dados_comuns.models import UnidadeAdministrativa


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
