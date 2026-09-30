from django.forms import Widget
from django.utils.html import format_html
from django.utils.safestring import mark_safe


class MovimentacaoLoteWidget(Widget):
    def value_from_datadict(self, data, files, name):
        return data.get(name)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = self.build_attrs(self.attrs, attrs)
        field_id = attrs.get("id", f"id_{name}")
        resolver_url = attrs.pop("data-resolver-url", "")
        attrs.pop("data-buscar-url", None)
        pesquisar_url = attrs.pop("data-pesquisar-url", "")
        value = value or ""
        hidden_input = format_html(
            '<input type="hidden" name="{}" id="{}" value="{}">',
            name,
            field_id,
            value,
        )
        return format_html(
            '<div class="movimentacao-lote" data-resolver-url="{resolver}" data-pesquisar-url="{pesquisar}">'
            '<div class="movimentacao-lote__modos" role="radiogroup" aria-label="Modo de seleção de bens">'
            '<label><input type="radio" name="{id}-modo" value="geral" checked> Buscar Geral</label>'
            '<label><input type="radio" name="{id}-modo" value="faixa"> Buscar Faixa</label>'
            '<label><input type="radio" name="{id}-modo" value="todos"> Todos os bens da UA</label></div>'
            '<div class="movimentacao-lote__criterio movimentacao-lote__criterio--geral">'
            '<label for="{id}-termo">Buscar por nome, descrição, ID ou número patrimonial</label>'
            '<input id="{id}-termo" class="movimentacao-lote__termo" type="search"></div>'
            '<div class="movimentacao-lote__criterio movimentacao-lote__criterio--faixa" hidden>'
            '<div><label for="{id}-busca-de">Número Patrimonial - De</label>'
            '<input id="{id}-busca-de" type="text" inputmode="numeric" maxlength="15" placeholder="000.000000000-0"></div>'
            '<div><label for="{id}-busca-ate">Número Patrimonial - Até</label>'
            '<input id="{id}-busca-ate" type="text" inputmode="numeric" maxlength="15" placeholder="000.000000000-0"></div></div>'
            '<button type="button" class="button movimentacao-lote__pesquisar">Buscar</button>'
            '<p class="movimentacao-lote__vazio" aria-live="polite"></p>'
            '<div class="movimentacao-lote__tabelas"><table class="movimentacao-lote__resultados">'
            '<thead><tr><th>Selecionar</th><th>ID</th><th>Número Patrimonial</th><th>Nome</th><th>Descrição</th><th>Localização</th><th>Situação</th></tr></thead><tbody></tbody></table></div>'
            '<button type="button" class="button movimentacao-lote__mais" hidden>Carregar mais</button>'
            '<p class="movimentacao-lote__erro" role="alert"></p>{hidden}</div>',
            resolver=resolver_url,
            pesquisar=pesquisar_url,
            id=field_id,
            hidden=mark_safe(hidden_input),
        )
