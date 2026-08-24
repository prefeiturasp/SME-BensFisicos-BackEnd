(function () {
  function getCsrfToken() {
    return document.cookie
      .split('; ')
      .find((cookie) => cookie.startsWith('csrftoken='))
      ?.split('=')[1]
  }

  function setError(erro, message) {
    erro.textContent = message || ''
  }

  function persist(hidden, state) {
    hidden.value = JSON.stringify({
      faixas: state.faixas.map(({ numero_patrimonial_de, numero_patrimonial_ate }) => ({
        numero_patrimonial_de,
        ...(numero_patrimonial_ate ? { numero_patrimonial_ate } : {}),
      })),
      selecionar_todos: state.selecionar_todos,
    })
  }

  function createModal(root, hiddenId) {
    const modal = document.createElement('div')
    const content = document.createElement('div')
    const title = document.createElement('h2')
    const close = document.createElement('button')
    const body = document.createElement('tbody')
    const table = document.createElement('table')
    const head = document.createElement('thead')
    const headRow = document.createElement('tr')

    modal.className = 'movimentacao-lote__modal'
    modal.hidden = true
    modal.setAttribute('role', 'dialog')
    modal.setAttribute('aria-modal', 'true')
    modal.setAttribute('aria-labelledby', `${hiddenId}-modal-title`)
    content.className = 'movimentacao-lote__modal-content'
    title.id = `${hiddenId}-modal-title`
    title.textContent = 'Bens da movimentação'
    close.type = 'button'
    close.className = 'button'
    close.textContent = 'Fechar'
    close.addEventListener('click', () => {
      modal.hidden = true
    })
    ;['Número Patrimonial', 'Nome do Bem', 'Status'].forEach((text) => {
      const th = document.createElement('th')
      th.textContent = text
      headRow.appendChild(th)
    })
    head.appendChild(headRow)
    table.className = 'movimentacao-lote__detalhes'
    table.append(head, body)
    content.append(title, close, table)
    modal.appendChild(content)
    root.appendChild(modal)

    return { modal, title, body, close }
  }

  function showModal(modal, titulo, itens) {
    modal.body.replaceChildren()
    itens.forEach((item) => {
      const tr = document.createElement('tr')
      ;[item.numero_patrimonial, item.nome, item.status].forEach((text) => {
        const td = document.createElement('td')
        td.textContent = text
        tr.appendChild(td)
      })
      modal.body.appendChild(tr)
    })
    modal.title.textContent = `Bens da movimentação: ${titulo}`
    modal.modal.hidden = false
    modal.close.focus()
  }

  function getRows(state) {
    if (state.selecionar_todos) {
      return [{ titulo: 'Todos os Bens aprovados da UA de origem', itens: state.todos, all: true }]
    }
    return state.faixas.map((faixa) => ({
      titulo: faixa.numero_patrimonial_ate
        ? `${faixa.numero_patrimonial_de} até ${faixa.numero_patrimonial_ate}`
        : faixa.numero_patrimonial_de,
      itens: faixa.itens,
      faixa,
    }))
  }

  function createButton(text, label, onClick) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = 'button'
    button.textContent = text
    button.setAttribute('aria-label', label)
    button.addEventListener('click', onClick)
    return button
  }

  function removeRow(state, row, selecionarTodos) {
    if (row.all) {
      state.selecionar_todos = false
      state.todos = []
      selecionarTodos.checked = false
      return
    }
    state.faixas = state.faixas.filter((faixa) => faixa !== row.faixa)
  }

  function createSummaryRow(row, state, controls, modal) {
    const tr = document.createElement('tr')
    const visualizar = createButton(
      '👁',
      `Visualizar bens da faixa ${row.titulo}`,
      () => showModal(modal, row.titulo, row.itens),
    )
    const remover = createButton('Excluir', `Excluir faixa ${row.titulo}`, () => {
      removeRow(state, row, controls.selecionarTodos)
      persist(controls.hidden, state)
      renderSummary(state, controls, modal)
    })

    ;[row.titulo, `${row.itens.length} bem(ns) selecionado(s)`].forEach((text) => {
      const td = document.createElement('td')
      td.textContent = text
      tr.appendChild(td)
    })
    const action = document.createElement('td')
    action.appendChild(visualizar)
    tr.appendChild(action)
    const apagar = document.createElement('td')
    apagar.appendChild(remover)
    tr.appendChild(apagar)
    return tr
  }

  function renderSummary(state, controls, modal) {
    controls.resumo.replaceChildren()
    getRows(state).forEach((row) => {
      controls.resumo.appendChild(createSummaryRow(row, state, controls, modal))
    })
    controls.de.disabled = state.selecionar_todos
    controls.ate.disabled = state.selecionar_todos
    controls.adicionar.disabled = state.selecionar_todos
    controls.root.classList.toggle('movimentacao-lote--todos', state.selecionar_todos)
  }

  async function resolver(url, origem, payload) {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() || '' },
      body: JSON.stringify({ unidade_administrativa_origem: origem.value, ...payload }),
    })
    const body = await response.json()
    if (!response.ok) throw new Error(body.detail || 'Não foi possível incluir os bens.')
    return body.itens
  }

  function hideOptions(opcoes) {
    opcoes.hidden = true
  }

  async function carregarOpcoes(controls, input) {
    if (!controls.origem.value) return
    const params = new URLSearchParams({
      unidade_administrativa_origem: controls.origem.value,
      q: input.value.trim(),
    })
    const response = await fetch(`${controls.buscarUrl}?${params.toString()}`)
    if (!response.ok) return
    const body = await response.json()
    controls.opcoes.replaceChildren()
    body.itens.forEach((item) => {
      const itemLista = document.createElement('li')
      const option = createButton(
        `${item.numero_patrimonial} - ${item.nome}`,
        `Selecionar ${item.numero_patrimonial}`,
        () => {
          input.value = item.numero_patrimonial
          hideOptions(controls.opcoes)
        },
      )
      itemLista.appendChild(option)
      controls.opcoes.appendChild(itemLista)
    })
    controls.opcoes.hidden = body.itens.length === 0
  }

  async function adicionarFaixa(state, controls, modal) {
    if (!controls.origem.value || !controls.de.value.trim()) {
      setError(controls.erro, 'Informe a Unidade Administrativa de origem e o Número Patrimonial - De.')
      return
    }
    setError(controls.erro, '')
    try {
      const faixa = {
        numero_patrimonial_de: controls.de.value.trim(),
        numero_patrimonial_ate: controls.ate.value.trim(),
      }
      const itens = await resolver(controls.url, controls.origem, { faixas: [faixa] })
      const ids = new Set(state.faixas.flatMap((item) => item.itens.map((bem) => bem.id)))
      if (itens.some((item) => ids.has(item.id))) {
        throw new Error('Os bens informados já foram adicionados à movimentação.')
      }
      state.faixas.push({ ...faixa, itens })
      controls.de.value = ''
      controls.ate.value = ''
      persist(controls.hidden, state)
      renderSummary(state, controls, modal)
    } catch (error) {
      setError(controls.erro, error instanceof Error ? error.message : 'Não foi possível incluir os bens.')
    }
  }

  async function atualizarSelecionarTodos(state, controls, modal) {
    if (!controls.selecionarTodos.checked) {
      state.selecionar_todos = false
      state.todos = []
      persist(controls.hidden, state)
      renderSummary(state, controls, modal)
      return
    }
    if (!controls.origem.value) {
      controls.selecionarTodos.checked = false
      setError(controls.erro, 'Informe a Unidade Administrativa de origem.')
      return
    }
    setError(controls.erro, '')
    try {
      state.todos = await resolver(controls.url, controls.origem, { selecionar_todos: true })
      state.faixas = []
      state.selecionar_todos = true
      persist(controls.hidden, state)
      renderSummary(state, controls, modal)
    } catch (error) {
      controls.selecionarTodos.checked = false
      setError(controls.erro, error instanceof Error ? error.message : 'Não foi possível incluir os bens.')
    }
  }

  function connectNumberFields(controls) {
    ;[controls.de, controls.ate].forEach((input) => {
      input.addEventListener('focus', () => void carregarOpcoes(controls, input))
      input.addEventListener('input', () => void carregarOpcoes(controls, input))
      input.addEventListener('blur', () => {
        globalThis.setTimeout(hideOptions, 150, controls.opcoes)
      })
    })
  }

  function resetOnOrigemChange(state, controls, modal) {
    state.faixas = []
    state.todos = []
    state.selecionar_todos = false
    controls.selecionarTodos.checked = false
    persist(controls.hidden, state)
    renderSummary(state, controls, modal)
  }

  function initialize(root) {
    const controls = {
      root,
      hidden: root.querySelector('input[type="hidden"]'),
      origem: document.getElementById('id_unidade_administrativa_origem'),
      de: root.querySelector('[id$="-de"]'),
      ate: root.querySelector('[id$="-ate"]'),
      adicionar: root.querySelector('.movimentacao-lote__adicionar'),
      selecionarTodos: root.querySelector('.movimentacao-lote__selecionar-todos'),
      resumo: root.querySelector('.movimentacao-lote__resumo tbody'),
      erro: root.querySelector('.movimentacao-lote__erro'),
      opcoes: root.querySelector('.movimentacao-lote__opcoes'),
      url: root.dataset.resolverUrl,
      buscarUrl: root.dataset.buscarUrl,
    }
    if (Object.values(controls).some((control) => !control)) return

    const state = { faixas: [], selecionar_todos: false, todos: [] }
    const modal = createModal(root, controls.hidden.id)
    controls.adicionar.addEventListener('click', () => void adicionarFaixa(state, controls, modal))
    controls.selecionarTodos.addEventListener('change', () =>
      void atualizarSelecionarTodos(state, controls, modal),
    )
    controls.origem.addEventListener('change', () => resetOnOrigemChange(state, controls, modal))
    connectNumberFields(controls)
    persist(controls.hidden, state)
    renderSummary(state, controls, modal)
  }

  function initializeAll() {
    document.querySelectorAll('.movimentacao-lote').forEach(initialize)
  }

  document.addEventListener('DOMContentLoaded', initializeAll)
})()
