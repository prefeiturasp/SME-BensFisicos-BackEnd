(function () {
  function getCsrfToken() {
    return document.cookie.split('; ').find((cookie) => cookie.startsWith('csrftoken='))?.split('=')[1]
  }

  function formatarNumeroPatrimonial(value) {
    const digits = value.replaceAll(/\D/g, '').slice(0, 13)
    if (digits.length <= 3) return digits
    if (digits.length <= 12) return `${digits.slice(0, 3)}.${digits.slice(3)}`
    return `${digits.slice(0, 3)}.${digits.slice(3, 12)}-${digits.slice(12)}`
  }

  function setError(controls, message) {
    controls.erro.textContent = message || ''
  }

  function newModeState(itens = []) {
    return { itens, resultados: [], proximaPagina: null, carregado: itens.length > 0, selecionarTodos: false, preservarSelecao: false }
  }

  function activeState(state) {
    return state.modos[state.modo]
  }

  function persist(state, controls) {
    const active = activeState(state)
    controls.hidden.value = JSON.stringify({
      modo: state.modo,
      selecionar_todos: active.selecionarTodos,
      itens: active.selecionarTodos ? [] : active.itens.map((bem) => bem.id),
      resumo: active.itens,
      estado_todos: {
        carregado: state.modos.todos.carregado,
        selecionar_todos: state.modos.todos.selecionarTodos,
      },
      resumos_por_modo: Object.fromEntries(
        Object.entries(state.modos).map(([modo, dados]) => [modo, dados.itens]),
      ),
    })
  }

  function readState(hidden) {
    const state = {
      modo: 'geral',
      modos: { geral: newModeState(), faixa: newModeState(), todos: newModeState() },
      faixasAntigas: [],
      versao: 0,
      busy: false,
    }
    try {
      const saved = JSON.parse(hidden.value || '{}')
      state.faixasAntigas = Array.isArray(saved.faixas) ? saved.faixas : []
      state.modo = ['geral', 'faixa', 'todos'].includes(saved.modo)
        ? saved.modo
        : (saved.selecionar_todos ? 'todos' : (state.faixasAntigas.length ? 'faixa' : 'geral'))
      for (const modo of Object.keys(state.modos)) {
        const resumo = saved.resumos_por_modo?.[modo]
        if (Array.isArray(resumo)) state.modos[modo] = newModeState(resumo)
      }
      const active = activeState(state)
      if (!active.itens.length && Array.isArray(saved.itens)) {
        const resumo = Array.isArray(saved.resumo) ? saved.resumo : []
        active.itens = saved.itens.map((id) => resumo.find((bem) => bem.id === id) || { id })
      }
      const todos = state.modos.todos
      todos.selecionarTodos = saved.estado_todos?.selecionar_todos === true
        || (state.modo === 'todos' && saved.selecionar_todos === true)
      if (saved.estado_todos?.carregado || todos.selecionarTodos) {
        todos.preservarSelecao = !todos.selecionarTodos
        todos.carregado = false
      }
    } catch {
      return state
    }
    return state
  }

  function appendCells(row, values) {
    values.forEach((value) => {
      const cell = document.createElement('td')
      cell.textContent = value
      row.appendChild(cell)
    })
  }

  function updateSelection(state, controls, bem, checked) {
    const active = activeState(state)
    active.itens = checked
      ? [...active.itens, bem]
      : active.itens.filter((item) => item.id !== bem.id)
    active.selecionarTodos = false
    if (state.modo === 'todos') active.preservarSelecao = true
    persist(state, controls)
    renderTable(state, controls)
  }

  function createRow(bem, state, controls) {
    const row = document.createElement('tr')
    const cell = document.createElement('td')
    const checkbox = document.createElement('input')
    checkbox.type = 'checkbox'
    checkbox.checked = activeState(state).itens.some((item) => item.id === bem.id)
    checkbox.disabled = bem.apto === false && !checkbox.checked
    checkbox.setAttribute('aria-label', `Selecionar bem ID ${bem.id}`)
    checkbox.addEventListener('change', () => updateSelection(state, controls, bem, checkbox.checked))
    cell.appendChild(checkbox)
    row.appendChild(cell)
    appendCells(row, [
      bem.id,
      bem.numero_patrimonial || 'Sem número patrimonial',
      bem.nome || '-',
      bem.descricao || '-',
      bem.localizacao || '-',
      bem.motivo || 'Apto para movimentação',
    ])
    return row
  }

  function renderTable(state, controls) {
    const active = activeState(state)
    const selectedIds = new Set(active.itens.map((bem) => bem.id))
    const rows = [
      ...active.itens,
      ...active.resultados.filter((bem) => !selectedIds.has(bem.id)),
    ]
    controls.resultados.replaceChildren(...rows.map((bem) => createRow(bem, state, controls)))
    controls.mais.hidden = !active.proximaPagina
  }

  function resetResults(state, controls) {
    state.versao += 1
    const active = activeState(state)
    active.resultados = []
    active.proximaPagina = null
    controls.vazio.textContent = ''
    renderTable(state, controls)
  }

  function applyMode(state, controls) {
    state.modo = controls.root.querySelector('input[name$="-modo"]:checked').value
    controls.geral.hidden = state.modo !== 'geral'
    controls.faixa.hidden = state.modo !== 'faixa'
    controls.pesquisar.hidden = state.modo === 'todos'
    controls.vazio.textContent = ''
    setError(controls, '')
    persist(state, controls)
    renderTable(state, controls)
    if (state.modo === 'todos' && !activeState(state).carregado) {
      void selecionarTodos(state, controls)
    }
  }

  function searchParams(controls, page) {
    const params = new URLSearchParams({ unidade_administrativa_origem: controls.origem.value, pagina: page })
    const mode = controls.root.querySelector('input[name$="-modo"]:checked').value
    if (mode === 'geral') {
      const term = controls.termo.value.trim()
      if (!term) throw new Error('Informe um critério de busca.')
      params.set('q', term)
      return params
    }
    const start = controls.de.value.trim()
    const end = controls.ate.value.trim()
    if (!start || (end && start > end)) {
      throw new Error('Informe um intervalo válido: o Número Patrimonial Até deve ser maior ou igual ao De.')
    }
    params.set('numero_patrimonial_de', start)
    if (end) params.set('numero_patrimonial_ate', end)
    return params
  }

  function setBusy(state, controls, busy) {
    state.busy = busy
    controls.pesquisar.disabled = busy
    controls.mais.disabled = busy
    controls.root.querySelectorAll('input[name$="-modo"]').forEach((radio) => {
      radio.disabled = busy
    })
  }

  async function pesquisarBens(state, controls, page = 1) {
    if (!controls.origem.value) {
      setError(controls, 'Informe a Unidade Administrativa de origem.')
      return
    }
    let params
    try {
      params = searchParams(controls, page)
    } catch (error) {
      setError(controls, error.message)
      return
    }
    const versao = ++state.versao
    setBusy(state, controls, true)
    setError(controls, '')
    try {
      const response = await fetch(`${controls.pesquisarUrl}?${params}`)
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Não foi possível buscar bens.')
      if (versao !== state.versao) return
      const active = activeState(state)
      active.resultados = page === 1 ? body.itens : [...active.resultados, ...body.itens]
      active.proximaPagina = body.proxima_pagina
      controls.vazio.textContent = body.count
        ? `${body.count} bem(ns) encontrado(s).`
        : 'A busca não retornou resultados.'
      renderTable(state, controls)
    } catch (error) {
      if (versao === state.versao) {
        setError(controls, error instanceof Error ? error.message : 'Não foi possível buscar bens.')
      }
    } finally {
      setBusy(state, controls, false)
    }
  }

  async function resolver(controls, payload) {
    const response = await fetch(controls.resolverUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() || '' },
      body: JSON.stringify({ unidade_administrativa_origem: controls.origem.value, ...payload }),
    })
    const body = await response.json()
    if (!response.ok) throw new Error(body.detail || 'Não foi possível incluir os bens.')
    return body.itens
  }

  async function selecionarTodos(state, controls) {
    if (!controls.origem.value) {
      setError(controls, 'Informe a Unidade Administrativa de origem.')
      return
    }
    const versao = ++state.versao
    setBusy(state, controls, true)
    setError(controls, '')
    try {
      const itens = await resolver(controls, { selecionar_todos: true })
      if (versao !== state.versao) return
      if (!itens.length) throw new Error('Nenhum bem aprovado foi encontrado na unidade administrativa de origem.')
      const active = state.modos.todos
      if (!active.preservarSelecao) active.itens = itens
      active.resultados = itens
      active.selecionarTodos = !active.preservarSelecao
      active.carregado = true
      persist(state, controls)
      renderTable(state, controls)
    } catch (error) {
      if (versao === state.versao) {
        setError(controls, error instanceof Error ? error.message : 'Não foi possível incluir os bens.')
      }
    } finally {
      setBusy(state, controls, false)
    }
  }

  async function restoreState(state, controls) {
    if (!controls.origem.value) return
    const versao = ++state.versao
    setBusy(state, controls, true)
    try {
      state.modos.faixa.itens = await resolver(controls, { faixas: state.faixasAntigas })
      if (versao !== state.versao) return
      state.faixasAntigas = []
      persist(state, controls)
      renderTable(state, controls)
    } catch (error) {
      if (versao === state.versao) {
        setError(controls, error instanceof Error ? error.message : 'Não foi possível restaurar os bens.')
      }
    } finally {
      setBusy(state, controls, false)
    }
  }

  function initialize(root) {
    const controls = {
      root,
      hidden: root.querySelector('input[type="hidden"]'),
      origem: document.getElementById('id_unidade_administrativa_origem'),
      geral: root.querySelector('.movimentacao-lote__criterio--geral'),
      faixa: root.querySelector('.movimentacao-lote__criterio--faixa'),
      termo: root.querySelector('.movimentacao-lote__termo'),
      de: root.querySelector('[id$="-busca-de"]'),
      ate: root.querySelector('[id$="-busca-ate"]'),
      pesquisar: root.querySelector('.movimentacao-lote__pesquisar'),
      resultados: root.querySelector('.movimentacao-lote__resultados tbody'),
      vazio: root.querySelector('.movimentacao-lote__vazio'),
      erro: root.querySelector('.movimentacao-lote__erro'),
      mais: root.querySelector('.movimentacao-lote__mais'),
      resolverUrl: root.dataset.resolverUrl,
      pesquisarUrl: root.dataset.pesquisarUrl,
    }
    if (Object.values(controls).some((control) => !control)) return
    const state = readState(controls.hidden)
    const form = root.closest('form')
    form?.addEventListener('submit', (event) => {
      if (!state.busy) return
      event.preventDefault()
      setError(controls, 'Aguarde a busca de bens terminar antes de salvar.')
    })
    root.querySelectorAll('input[name$="-modo"]').forEach((radio) => {
      radio.addEventListener('change', () => applyMode(state, controls))
    })
    controls.termo.addEventListener('input', () => resetResults(state, controls))
    ;[controls.de, controls.ate].forEach((input) => {
      input.addEventListener('input', () => {
        input.value = formatarNumeroPatrimonial(input.value)
        resetResults(state, controls)
      })
    })
    controls.pesquisar.addEventListener('click', () => void pesquisarBens(state, controls))
    controls.mais.addEventListener('click', () => void pesquisarBens(state, controls, activeState(state).proximaPagina))
    controls.origem.addEventListener('change', () => {
      state.versao += 1
      state.modos = { geral: newModeState(), faixa: newModeState(), todos: newModeState() }
      state.modo = 'geral'
      root.querySelector('input[value="geral"]').checked = true
      persist(state, controls)
      applyMode(state, controls)
    })
    root.querySelector(`input[value="${state.modo}"]`).checked = true
    applyMode(state, controls)
    if (state.faixasAntigas.length) void restoreState(state, controls)
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.movimentacao-lote').forEach(initialize)
  })
})()
