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
        buscar_url = attrs.pop("data-buscar-url", "")
        pesquisar_url = attrs.pop("data-pesquisar-url", "")
        value = value or ""
        hidden_input = format_html(
            '<input type="hidden" name="{}" id="{}" value="{}">',
            name,
            field_id,
            value,
        )
        return format_html(
            '<div class="movimentacao-lote" data-resolver-url="{}" data-buscar-url="{}" data-pesquisar-url="{}">'
            '<fieldset class="movimentacao-lote__busca"><legend>Buscar e selecionar bens</legend>'
            '<label for="{}-tipo">Buscar por</label><select id="{}-tipo" class="movimentacao-lote__tipo">'
            '<option value="numero_patrimonial">Número Patrimonial</option><option value="id">ID</option>'
            '<option value="intervalo">Intervalo Patrimonial</option><option value="descricao">Descrição</option></select>'
            '<label for="{}-termo" class="movimentacao-lote__termo-label">Termo</label><input id="{}-termo" class="movimentacao-lote__termo" type="text">'
            '<div class="movimentacao-lote__intervalo" hidden>'
            '<label for="{}-busca-de">Número Patrimonial - De</label><input id="{}-busca-de" type="text">'
            '<label for="{}-busca-ate">Número Patrimonial - Até</label><input id="{}-busca-ate" type="text"></div>'
            '<button type="button" class="button movimentacao-lote__pesquisar">Buscar</button>'
            '<p class="movimentacao-lote__vazio" aria-live="polite"></p>'
            '<div class="movimentacao-lote__tabelas"><table class="movimentacao-lote__resultados">'
            '<thead><tr><th>Selecionar</th><th>ID</th><th>Número Patrimonial</th><th>Descrição</th><th>Localização</th><th>Situação</th></tr></thead><tbody></tbody></table>'
            '<button type="button" class="button movimentacao-lote__mais" hidden>Carregar mais</button>'
            '<h3 class="movimentacao-lote__selecionados-titulo">Bens selecionados</h3><table class="movimentacao-lote__selecionados">'
            '<thead><tr><th>ID</th><th>Número Patrimonial</th><th>Descrição</th><th>Localização</th><th>Ação</th></tr></thead><tbody></tbody></table></div>'
            '</fieldset><h3 class="movimentacao-lote__faixa-titulo">Adicionar faixa inteira</h3>'
            '<div class="movimentacao-lote__inputs">'
            '<div><label for="{}-de">Número Patrimonial - De</label>'
            '<input id="{}-de" type="text" inputmode="numeric" maxlength="15" '
            'placeholder="000.000000000-0"></div>'
            '<div><label for="{}-ate">Número Patrimonial - Até</label>'
            '<input id="{}-ate" type="text" inputmode="numeric" maxlength="15" '
            'placeholder="000.000000000-0"></div>'
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
            pesquisar_url,
            field_id,
            field_id,
            field_id,
            field_id,
            field_id,
            field_id,
            field_id,
            field_id,
            field_id,
            field_id,
            field_id,
            field_id,
            mark_safe(hidden_input),
        )
