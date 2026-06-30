from import_export import fields, resources

from usuario.models import Usuario


class UsuarioResource(resources.ModelResource):
    nome = fields.Field(column_name="Nome", attribute="nome")
    rf = fields.Field(column_name="RF", attribute="rf")
    email = fields.Field(column_name="E-mail", attribute="email")
    unidade_administrativa = fields.Field(column_name="Unidade Administrativa")

    class Meta:
        model = Usuario
        fields = ("nome", "rf", "email", "unidade_administrativa")
        export_order = ("nome", "rf", "email", "unidade_administrativa")

    def dehydrate_unidade_administrativa(self, usuario):
        if not usuario.unidade_administrativa:
            return "-"

        return str(usuario.unidade_administrativa)
