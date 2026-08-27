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

  function formatarNumeroPatrimonial(value) {
    const digits = value.replace(/\D/g, '').slice(0, 13)
    if (digits.length <= 3) return digits
    if (digits.length <= 12) return `${digits.slice(0, 3)}.${digits.slice(3)}`
    return `${digits.slice(0, 3)}.${digits.slice(3, 12)}-${digits.slice(12)}`
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

  function readState(hidden) {
    try {
      const value = JSON.parse(hidden.value || '{}')
      return {
        faixas: Array.isArray(value.faixas)
          ? value.faixas.map((faixa) => ({ ...faixa, itens: [] }))
          : [],
        selecionar_todos: value.selecionar_todos === true,
        todos: [],
      }
    } catch {
      return { faixas: [], selecionar_todos: false, todos: [] }
    }
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

  function createSummaryRow(row, state, controls) {
    const tr = document.createElement('tr')
    const remover = createButton('Excluir', `Excluir faixa ${row.titulo}`, () => {
      removeRow(state, row, controls.selecionarTodos)
      persist(controls.hidden, state)
      renderSummary(state, controls)
    })
    const nomes = row.itens.map((item) => item.nome).join(', ')

    ;[row.titulo, nomes].forEach((text) => {
      const td = document.createElement('td')
      td.textContent = text
      tr.appendChild(td)
    })
    const action = document.createElement('td')
    action.appendChild(remover)
    tr.appendChild(action)
    return tr
  }

  function renderSummary(state, controls) {
    controls.resumo.replaceChildren()
    getRows(state).forEach((row) => {
      controls.resumo.appendChild(createSummaryRow(row, state, controls))
    })
    controls.de.disabled = state.selecionar_todos
    controls.ate.disabled = state.selecionar_todos
    controls.adicionar.disabled = state.selecionar_todos
    controls.selecionarTodos.checked = state.selecionar_todos
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

  function faixaDuplicada(state, faixa) {
    return state.faixas.some(
      (item) =>
        item.numero_patrimonial_de === faixa.numero_patrimonial_de &&
        item.numero_patrimonial_ate === faixa.numero_patrimonial_ate,
    )
  }

  async function adicionarFaixa(state, controls) {
    if (!controls.origem.value || !controls.de.value.trim()) {
      setError(controls.erro, 'Informe a Unidade Administrativa de origem e o Número Patrimonial - De.')
      return
    }
    const faixa = {
      numero_patrimonial_de: controls.de.value.trim(),
      numero_patrimonial_ate: controls.ate.value.trim(),
    }
    if (faixa.numero_patrimonial_ate && faixa.numero_patrimonial_ate < faixa.numero_patrimonial_de) {
      setError(controls.erro, 'O Número Patrimonial Até deve ser maior ou igual ao Número Patrimonial De.')
      return
    }
    if (faixaDuplicada(state, faixa)) {
      setError(controls.erro, 'A faixa informada já foi adicionada à movimentação.')
      return
    }

    setError(controls.erro, '')
    try {
      const itens = await resolver(controls.url, controls.origem, { faixas: [faixa] })
      const ids = new Set(state.faixas.flatMap((item) => item.itens.map((bem) => bem.id)))
      if (itens.some((item) => ids.has(item.id))) {
        throw new Error('Os bens informados já foram adicionados à movimentação.')
      }
      state.faixas.push({ ...faixa, itens })
      controls.de.value = ''
      controls.ate.value = ''
      persist(controls.hidden, state)
      renderSummary(state, controls)
    } catch (error) {
      setError(controls.erro, error instanceof Error ? error.message : 'Não foi possível incluir os bens.')
    }
  }

  async function atualizarSelecionarTodos(state, controls) {
    if (!controls.selecionarTodos.checked) {
      state.selecionar_todos = false
      state.todos = []
      persist(controls.hidden, state)
      renderSummary(state, controls)
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
      renderSummary(state, controls)
    } catch (error) {
      controls.selecionarTodos.checked = false
      setError(controls.erro, error instanceof Error ? error.message : 'Não foi possível incluir os bens.')
    }
  }

  function connectNumberFields(controls) {
    ;[controls.de, controls.ate].forEach((input) => {
      input.addEventListener('focus', () => void carregarOpcoes(controls, input))
      input.addEventListener('input', () => {
        input.value = formatarNumeroPatrimonial(input.value)
        void carregarOpcoes(controls, input)
      })
      input.addEventListener('blur', () => {
        globalThis.setTimeout(hideOptions, 150, controls.opcoes)
      })
    })
  }

  function resetOnOrigemChange(state, controls) {
    state.faixas = []
    state.todos = []
    state.selecionar_todos = false
    controls.selecionarTodos.checked = false
    persist(controls.hidden, state)
    renderSummary(state, controls)
  }

  async function restoreState(state, controls) {
    if (!controls.origem.value) return
    try {
      if (state.selecionar_todos) {
        state.todos = await resolver(controls.url, controls.origem, { selecionar_todos: true })
      } else {
        const itensPorFaixa = await Promise.all(
          state.faixas.map((faixa) => resolver(controls.url, controls.origem, { faixas: [faixa] })),
        )
        state.faixas.forEach((faixa, index) => {
          faixa.itens = itensPorFaixa[index]
        })
      }
      renderSummary(state, controls)
    } catch (error) {
      setError(controls.erro, error instanceof Error ? error.message : 'Não foi possível restaurar os bens.')
    }
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

    const state = readState(controls.hidden)
    controls.adicionar.addEventListener('click', () => void adicionarFaixa(state, controls))
    controls.selecionarTodos.addEventListener('change', () =>
      void atualizarSelecionarTodos(state, controls),
    )
    controls.origem.addEventListener('change', () => resetOnOrigemChange(state, controls))
    connectNumberFields(controls)
    renderSummary(state, controls)
    void restoreState(state, controls)
  }

  function initializeAll() {
    document.querySelectorAll('.movimentacao-lote').forEach(initialize)
  }

  document.addEventListener('DOMContentLoaded', initializeAll)
})()
