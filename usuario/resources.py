from import_export import fields, resources
from tablib import Dataset

from usuario.constants import GRUPO_OPERADOR_INVENTARIO
from usuario.models import Usuario


class UsuarioResource(resources.ModelResource):
    nome = fields.Field(column_name="Nome do Operador", attribute="nome")
    rf = fields.Field(column_name="RF", attribute="rf")
    email = fields.Field(column_name="E-mail", attribute="email")
    unidade_administrativa = fields.Field(column_name="Unidade Administrativa")

    class Meta:
        model = Usuario
        fields = ("nome", "rf", "email", "unidade_administrativa")
        export_order = ("nome", "rf", "email", "unidade_administrativa")

    def _listar_unidades_administrativas(self, usuario):
        unidades = list(usuario.uas_permitidas.order_by("codigo", "id"))
        if not unidades and usuario.unidade_administrativa:
            unidades = [usuario.unidade_administrativa]
        return unidades

    def export(self, queryset=None, **kwargs):
        if queryset is None:
            queryset = self.get_queryset()

        usuarios = list(
            queryset.filter(groups__name=GRUPO_OPERADOR_INVENTARIO).distinct()
        )
        dataset = Dataset()
        max_unidades = max(
            (len(self._listar_unidades_administrativas(usuario)) for usuario in usuarios),
            default=1,
        )

        headers = ["Nome do Operador", "RF", "E-mail"]
        headers.extend([f"UA {indice}" for indice in range(1, max_unidades + 1)])
        dataset.headers = headers

        for usuario in usuarios:
            unidades = self._listar_unidades_administrativas(usuario)
            row = [usuario.nome, usuario.rf, usuario.email]
            row.extend(str(unidade) for unidade in unidades)
            row.extend([""] * (max_unidades - len(unidades)))
            dataset.append(row)

        return dataset
