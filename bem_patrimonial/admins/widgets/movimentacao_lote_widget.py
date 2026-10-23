from django.forms import Widget
from django.templatetags.static import static
from django.utils.html import format_html
from django.utils.safestring import mark_safe


AJUDAS_MOVIMENTACAO = {
    "faixa": (
        "Encontre bens da UA de origem pelo intervalo de números patrimoniais informado. "
        "Clique em Buscar para conferir os resultados e em Importar Faixa para adicioná-los aos selecionados."
    ),
    "de": (
        "Informe o número patrimonial completo do primeiro bem que deseja buscar, "
        "exatamente como aparece no cadastro."
    ),
    "ate": (
        "Informe o número patrimonial do último bem que deseja buscar. "
        "Se Até não for preenchido, a busca procurará exatamente o número informado em De."
    ),
    "regras": (
        "Podem ser adicionados bens da UA de origem com status Aprovado, sem bloqueio por inventário "
        "e sem outra movimentação pendente. Bens já selecionados não podem ser adicionados novamente. "
        "Aparecer na busca não significa que o bem pode ser adicionado."
    ),
    "importar": (
        "Adiciona os bens da faixa aos selecionados. Se algum número não existir na UA, algum bem "
        "estiver impedido ou já estiver selecionado, nenhum bem dessa faixa será adicionado. "
        "Cada faixa pode ter até 500 bens."
    ),
    "sequencia": (
        "O dígito após o hífen não é considerado para calcular a sequência. "
        "Por exemplo, De 001.000000010-0 até 001.000000012-0 busca os bens 010, 011 e 012, "
        "independentemente do dígito final. Todos os números da sequência devem existir na UA "
        "de origem e estar aptos para movimentação. Se Até ficar vazio, a busca será exata pelo número informado em De."
    ),
}


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
            '<div class="movimentacao-lote" data-edit-icon="{edit_icon}" data-remove-icon="{remove_icon}" data-resolver-url="{resolver}" data-buscar-url="{buscar}" data-pesquisar-url="{pesquisar}">'
            '<div class="movimentacao-lote__modos" role="radiogroup" aria-label="Modo de seleção de bens">'
            '<label><input type="radio" name="{id}-modo" value="manual" checked> Seleção manual</label>'
            '<label><input type="radio" name="{id}-modo" value="todos"> Todos os bens da UA</label></div>'
            '<div class="movimentacao-lote__abas" role="tablist" aria-label="Tipo de busca manual">'
            '<button type="button" role="tab" data-modo="geral" aria-selected="true">Busca geral</button>'
            '<button type="button" role="tab" data-modo="faixa" aria-selected="false">Busca por faixa</button>'
            '<button type="button" role="tab" data-modo="visualizar" aria-selected="false">Visualizar todos</button></div>'
            '<p class="movimentacao-lote__visualizar" hidden>Confira os bens da UA de origem e marque os que deseja movimentar. Bens impedidos e itens de faixas selecionadas permanecem bloqueados.</p>'
            '<div class="movimentacao-lote__criterio movimentacao-lote__criterio--geral">'
            '<label for="{id}-termo">Buscar por nome, descrição, ID ou número patrimonial</label>'
            '<input id="{id}-termo" class="movimentacao-lote__termo" type="text"></div>'
            '<div class="movimentacao-lote__criterio movimentacao-lote__criterio--faixa" hidden>'
            '<div class="movimentacao-lote__ajuda-faixa">'
            '<span>Como buscar por faixa <span class="movimentacao-lote__ajuda" role="img" tabindex="0" aria-label="{ajuda_faixa}">?</span></span>'
            '<span>Exemplos de faixa <span class="movimentacao-lote__ajuda" role="img" tabindex="0" aria-label="{ajuda_sequencia}">?</span></span></div>'
            '<div><div class="movimentacao-lote__rotulo"><label for="{id}-busca-de">Número Patrimonial - De</label>'
            '<span class="movimentacao-lote__ajuda" role="img" tabindex="0" aria-label="{ajuda_de}">?</span></div>'
            '<input id="{id}-busca-de" type="text" inputmode="numeric" maxlength="15" placeholder="000.000000000-0"></div>'
            '<div><div class="movimentacao-lote__rotulo"><label for="{id}-busca-ate">Número Patrimonial - Até</label>'
            '<span class="movimentacao-lote__ajuda" role="img" tabindex="0" aria-label="{ajuda_ate}">?</span></div>'
            '<input id="{id}-busca-ate" type="text" inputmode="numeric" maxlength="15" placeholder="000.000000000-0"></div></div>'
            '<ul class="movimentacao-lote__opcoes" hidden></ul>'
            '<div class="movimentacao-lote__acoes">'
            '<button type="button" class="button movimentacao-lote__pesquisar">Buscar</button>'
            '<button type="button" class="button movimentacao-lote__importar" hidden>Importar Faixa</button>'
            '<span class="movimentacao-lote__ajuda movimentacao-lote__ajuda-importar" role="img" tabindex="0" aria-label="{ajuda_importar}" hidden>?</span></div>'
            '<p class="movimentacao-lote__vazio" aria-live="polite"></p>'
            '<h3 class="movimentacao-lote__resultados-titulo" hidden>Resultados da Busca (0)</h3>'
            '<div class="movimentacao-lote__tabelas"><table class="movimentacao-lote__resultados">'
            '<thead><tr><th class="movimentacao-lote__coluna-selecao"><input type="checkbox" class="movimentacao-lote__selecionar-resultados" aria-label="Selecionar todos os resultados"></th>'
            '<th>ID</th><th>Número Patrimonial</th><th>Nome</th><th>Descrição</th><th>Localização</th>'
            '<th>Situação <span class="movimentacao-lote__ajuda" role="img" tabindex="0" aria-label="{ajuda_regras}">?</span></th></tr></thead><tbody></tbody></table></div>'
            '<button type="button" class="button movimentacao-lote__mais" hidden>Carregar mais</button>'
            '<h3 class="movimentacao-lote__selecionados-titulo">Selecionados (0)</h3>'
            '<div class="movimentacao-lote__tabelas"><table class="movimentacao-lote__selecionados">'
            '<thead><tr><th>Número Patrimonial</th><th>Quantidade</th><th>Nome do Bem</th><th>Ação</th></tr></thead>'
            '<tbody><tr class="movimentacao-lote__sem-selecao"><td colspan="4">Nenhum bem selecionado.</td></tr></tbody></table></div>'
            '<p class="movimentacao-lote__erro" role="alert"></p>{hidden}</div>',
            resolver=resolver_url,
            buscar=buscar_url,
            pesquisar=pesquisar_url,
            edit_icon=static("admin/img/icon-changelink.svg"),
            remove_icon=static("admin/img/icon-deletelink.svg"),
            id=field_id,
            hidden=mark_safe(hidden_input),
            ajuda_faixa=AJUDAS_MOVIMENTACAO["faixa"],
            ajuda_de=AJUDAS_MOVIMENTACAO["de"],
            ajuda_ate=AJUDAS_MOVIMENTACAO["ate"],
            ajuda_regras=AJUDAS_MOVIMENTACAO["regras"],
            ajuda_importar=AJUDAS_MOVIMENTACAO["importar"],
            ajuda_sequencia=AJUDAS_MOVIMENTACAO["sequencia"],
        )
