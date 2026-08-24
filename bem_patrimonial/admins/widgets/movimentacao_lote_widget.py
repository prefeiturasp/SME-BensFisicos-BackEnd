from django.forms import Widget
from django.utils.html import format_html
from django.utils.safestring import mark_safe


class MovimentacaoLoteWidget(Widget):
    def value_from_datadict(self, data, files, name):
        return data.get(name)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = dict(attrs or {})
        field_id = attrs.get("id", f"id_{name}")
        resolver_url = attrs.pop("data-resolver-url", "")
        buscar_url = attrs.pop("data-buscar-url", "")
        value = value or ""
        hidden_input = format_html(
            '<input type="hidden" name="{}" id="{}" value="{}">',
            name,
            field_id,
            value,
        )
        return format_html(
            '<div class="movimentacao-lote" data-resolver-url="{}" data-buscar-url="{}">'
            '<div class="movimentacao-lote__inputs">'
            '<div><label for="{}-de">Número Patrimonial - De</label>'
            '<input id="{}-de" type="text" placeholder="000.000000000-0"></div>'
            '<div><label for="{}-ate">Número Patrimonial - Até</label>'
            '<input id="{}-ate" type="text" placeholder="000.000000000-0"></div>'
            '<button type="button" class="button movimentacao-lote__adicionar">Adicionar</button>'
            '</div>'
            '<ul class="movimentacao-lote__opcoes" hidden></ul>'
            '<label class="movimentacao-lote__todos">'
            '<input type="checkbox" class="movimentacao-lote__selecionar-todos">'
            ' Selecionar todos os Bens aprovados da UA de origem</label>'
            '<p class="movimentacao-lote__erro" role="alert"></p>'
            '<table class="movimentacao-lote__resumo">'
            '<thead><tr><th>Número Patrimonial</th><th>Nome do Bem</th><th>Ação</th></tr></thead>'
            '<tbody></tbody></table>{}'
            '</div>',
            resolver_url,
            buscar_url,
            field_id,
            field_id,
            field_id,
            field_id,
            mark_safe(hidden_input),
        )
