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

  function selectionIds(selections) {
    return new Set(selections.flatMap((selection) => selection.bens.map((bem) => bem.id)))
  }

  function blockedIds(selections) {
    return new Set(selections.filter((selection) => selection.tipo !== 'individual')
      .flatMap((selection) => selection.bens.map((bem) => bem.id)))
  }

  function setError(controls, message) {
    controls.erro.textContent = message || ''
  }

  function createInitialState(hidden) {
    const state = {
      modo: 'geral', selecoes: [], resultados: [], proximaPagina: null,
      total: 0, faixasAntigas: [], versao: 0, busy: false,
    }
    try {
      const saved = JSON.parse(hidden.value || '{}')
      state.faixasAntigas = Array.isArray(saved.faixas) ? saved.faixas : []
      state.modo = ['geral', 'faixa', 'todos'].includes(saved.modo) ? saved.modo : 'geral'
      if (Array.isArray(saved.selecoes)) {
        state.selecoes = saved.selecoes
        return state
      }
      const resumo = Array.isArray(saved.resumo) ? saved.resumo : (saved.resumos_por_modo?.[state.modo] || [])
      if (saved.selecionar_todos && resumo.length) {
        state.selecoes = [{ id: 'todos', tipo: 'todos', bens: resumo }]
      } else {
        const ids = new Set(Array.isArray(saved.itens) ? saved.itens : resumo.map((bem) => bem.id))
        state.selecoes = resumo.filter((bem) => ids.has(bem.id))
          .map((bem) => ({ id: `bem-${bem.id}`, tipo: 'individual', bens: [bem] }))
      }
    } catch {
      return state
    }
    return state
  }

  function persist(state, controls) {
    const allGoods = state.selecoes.flatMap((selection) => selection.bens)
    const bens = [...selectionIds(state.selecoes)].map((id) => allGoods.find((bem) => bem.id === id))
    const selecionarTodos = state.selecoes.length === 1 && state.selecoes[0].tipo === 'todos'
    controls.hidden.value = JSON.stringify({
      modo: state.modo,
      selecionar_todos: selecionarTodos,
      itens: selecionarTodos ? [] : bens.map((bem) => bem.id),
      resumo: bens,
      selecoes: state.selecoes,
    })
  }

  function appendCells(row, values) {
    values.forEach((value) => {
      const cell = document.createElement('td')
      cell.textContent = value
      row.appendChild(cell)
    })
  }

  function toggleIndividual(state, controls, bem, checked) {
    if (checked) {
      state.selecoes.push({ id: `bem-${bem.id}`, tipo: 'individual', bens: [bem] })
    } else {
      state.selecoes = state.selecoes.filter(
        (selection) => selection.tipo !== 'individual' || selection.bens[0].id !== bem.id,
      )
    }
    setError(controls, '')
    persist(state, controls)
    render(state, controls)
  }

  function createResultRow(bem, state, controls) {
    const selected = selectionIds(state.selecoes)
    const blocked = blockedIds(state.selecoes)
    const row = document.createElement('tr')
    const cell = document.createElement('td')
    const checkbox = document.createElement('input')
    checkbox.type = 'checkbox'
    checkbox.checked = selected.has(bem.id)
    checkbox.disabled = state.modo !== 'geral' || bem.apto === false || blocked.has(bem.id)
    checkbox.setAttribute('aria-label', `Selecionar bem ID ${bem.id}`)
    checkbox.addEventListener('change', () => toggleIndividual(state, controls, bem, checkbox.checked))
    cell.appendChild(checkbox)
    row.appendChild(cell)
    appendCells(row, [bem.id, bem.numero_patrimonial || 'Sem número patrimonial', bem.nome || '-',
      bem.descricao || '-', bem.localizacao || '-', bem.motivo || 'Apto para movimentação'])
    return row
  }

  function selectionLabel(selection) {
    if (selection.tipo === 'todos') return 'Todos os bens aptos da UA de origem'
    if (selection.tipo === 'faixa') {
      return selection.numeroAte && selection.numeroAte !== selection.numeroDe
        ? `${selection.numeroDe} até ${selection.numeroAte}` : selection.numeroDe
    }
    const bem = selection.bens[0]
    return bem.numero_patrimonial || `ID ${bem.id}`
  }

  function createSelectionRow(selection, state, controls) {
    const row = document.createElement('tr')
    const names = selection.tipo === 'todos'
      ? `${selection.bens.length} bem(ns) selecionado(s)`
      : selection.bens.map((bem) => bem.nome || '-').join(', ')
    appendCells(row, [selectionLabel(selection), selection.bens.length, names])
    const action = document.createElement('td')
    const remove = document.createElement('button')
    remove.type = 'button'
    remove.className = 'button movimentacao-lote__remover'
    remove.textContent = 'Remover'
    remove.setAttribute('aria-label', `Remover seleção ${selectionLabel(selection)}`)
    remove.addEventListener('click', () => {
      state.selecoes = state.selecoes.filter((item) => item.id !== selection.id)
      persist(state, controls)
      render(state, controls)
    })
    action.appendChild(remove)
    row.appendChild(action)
    return row
  }

  function updateHeaderCheckbox(state, controls) {
    const selected = selectionIds(state.selecoes)
    const blocked = blockedIds(state.selecoes)
    const selectable = state.modo === 'geral'
      ? state.resultados.filter((bem) => bem.apto !== false && !blocked.has(bem.id)) : []
    const selectedCount = selectable.filter((bem) => selected.has(bem.id)).length
    controls.selecionarResultados.disabled = !selectable.length
    controls.selecionarResultados.checked = selectable.length > 0 && selectedCount === selectable.length
    controls.selecionarResultados.indeterminate = selectedCount > 0 && selectedCount < selectable.length
  }

  function render(state, controls) {
    controls.resultados.replaceChildren(...state.resultados.map((bem) => createResultRow(bem, state, controls)))
    controls.tituloSelecionados.textContent = `Selecionados (${selectionIds(state.selecoes).size})`
    if (state.selecoes.length) {
      controls.selecionados.replaceChildren(
        ...state.selecoes.map((selection) => createSelectionRow(selection, state, controls)),
      )
    } else {
      const row = document.createElement('tr')
      const cell = document.createElement('td')
      cell.colSpan = 4
      cell.textContent = 'Nenhum bem selecionado.'
      row.appendChild(cell)
      controls.selecionados.replaceChildren(row)
    }
    controls.mais.hidden = !state.proximaPagina
    controls.importar.hidden = state.modo !== 'faixa' || state.total === 0
    updateHeaderCheckbox(state, controls)
  }

  function resetResults(state, controls) {
    state.versao += 1
    state.resultados = []
    state.proximaPagina = null
    state.total = 0
    controls.vazio.textContent = ''
    render(state, controls)
  }

  function setModeLayout(state, controls) {
    controls.geral.hidden = state.modo !== 'geral'
    controls.faixa.hidden = state.modo !== 'faixa'
    controls.pesquisar.hidden = state.modo === 'todos'
    controls.importar.hidden = state.modo !== 'faixa' || state.total === 0
    controls.vazio.textContent = ''
    setError(controls, '')
    persist(state, controls)
    render(state, controls)
  }

  function searchParams(state, controls, page) {
    const params = new URLSearchParams({ unidade_administrativa_origem: controls.origem.value, pagina: page })
    if (state.modo === 'geral') {
      const term = controls.termo.value.trim()
      if (!term) throw new Error('Informe um critério de busca.')
      params.set('termo_busca', term)
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
    controls.importar.disabled = busy
    controls.mais.disabled = busy
    controls.selecionarResultados.disabled = busy
    controls.root.querySelectorAll('input[name$="-modo"]').forEach((radio) => { radio.disabled = busy })
  }

  async function pesquisarBens(state, controls, page = 1) {
    if (!controls.origem.value) {
      setError(controls, 'Informe a Unidade Administrativa de origem.')
      return
    }
    let params
    try {
      params = searchParams(state, controls, page)
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
      state.resultados = page === 1 ? body.itens : [...state.resultados, ...body.itens]
      state.proximaPagina = body.proxima_pagina
      state.total = body.count
      controls.vazio.textContent = body.count ? `${body.count} bem(ns) encontrado(s).` : 'A busca não retornou resultados.'
      render(state, controls)
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

  async function importarFaixa(state, controls) {
    let params
    try {
      params = searchParams(state, controls, 1)
    } catch (error) {
      setError(controls, error.message)
      return
    }
    const numeroDe = params.get('numero_patrimonial_de')
    const numeroAteInformado = params.get('numero_patrimonial_ate')
    const numeroAte = numeroAteInformado || numeroDe
    const faixaRepetida = state.selecoes.some((selection) => selection.tipo === 'faixa'
      && selection.numeroDe === numeroDe && selection.numeroAte === numeroAte)
    if (faixaRepetida) {
      setError(controls, 'A faixa informada já foi adicionada à movimentação.')
      return
    }
    setBusy(state, controls, true)
    setError(controls, '')
    try {
      const itens = await resolver(controls, {
        faixas: [{
          numero_patrimonial_de: numeroDe,
          ...(numeroAteInformado ? { numero_patrimonial_ate: numeroAteInformado } : {}),
        }],
      })
      if (!itens.length) throw new Error('Nenhum bem apto foi encontrado na faixa informada.')
      const selected = selectionIds(state.selecoes)
      if (itens.some((bem) => selected.has(bem.id))) {
        throw new Error('Um ou mais bens da faixa já foram adicionados à movimentação.')
      }
      state.selecoes.push({ id: `faixa-${numeroDe}-${numeroAte}`, tipo: 'faixa', numeroDe, numeroAte, bens: itens })
      controls.de.value = ''
      controls.ate.value = ''
      resetResults(state, controls)
      persist(state, controls)
    } catch (error) {
      setError(controls, error instanceof Error ? error.message : 'Não foi possível importar a faixa.')
    } finally {
      setBusy(state, controls, false)
    }
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
      state.selecoes = [{ id: 'todos', tipo: 'todos', bens: itens }]
      state.resultados = itens
      state.total = itens.length
      state.proximaPagina = null
      persist(state, controls)
      render(state, controls)
    } catch (error) {
      if (versao === state.versao) {
        setError(controls, error instanceof Error ? error.message : 'Não foi possível incluir os bens.')
      }
    } finally {
      setBusy(state, controls, false)
    }
  }

  function changeMode(state, controls, newMode) {
    const previousMode = state.modo
    const sairDaSelecaoDeTodos = previousMode === 'todos' && newMode !== 'todos'
    state.modo = newMode
    if (sairDaSelecaoDeTodos) {
      state.selecoes = []
    }
    resetResults(state, controls)
    if (newMode !== 'todos') {
      setModeLayout(state, controls)
      return
    }
    const confirmed = !state.selecoes.length || window.confirm(
      'A lista de bens selecionados será substituída por todos os bens aptos da Unidade Administrativa de origem. Deseja continuar?',
    )
    if (!confirmed) {
      state.modo = previousMode
      controls.root.querySelector(`input[value="${previousMode}"]`).checked = true
      setModeLayout(state, controls)
      return
    }
    setModeLayout(state, controls)
    void selecionarTodos(state, controls)
  }

  function toggleVisibleResults(state, controls) {
    if (state.modo !== 'geral') return
    const blocked = blockedIds(state.selecoes)
    const selectable = state.resultados.filter((bem) => bem.apto !== false && !blocked.has(bem.id))
    const selected = selectionIds(state.selecoes)
    const remove = selectable.length > 0 && selectable.every((bem) => selected.has(bem.id))
    const visibleIds = new Set(selectable.map((bem) => bem.id))
    if (remove) {
      state.selecoes = state.selecoes.filter(
        (selection) => selection.tipo !== 'individual' || !visibleIds.has(selection.bens[0].id),
      )
    } else {
      selectable.filter((bem) => !selected.has(bem.id))
        .forEach((bem) => state.selecoes.push({ id: `bem-${bem.id}`, tipo: 'individual', bens: [bem] }))
    }
    persist(state, controls)
    render(state, controls)
  }

  async function restoreLegacyRanges(state, controls) {
    if (!controls.origem.value || !state.faixasAntigas.length) return
    setBusy(state, controls, true)
    try {
      for (const [index, faixa] of state.faixasAntigas.entries()) {
        const itens = await resolver(controls, { faixas: [faixa] })
        state.selecoes.push({
          id: `faixa-restaurada-${index}`, tipo: 'faixa',
          numeroDe: faixa.numero_patrimonial_de,
          numeroAte: faixa.numero_patrimonial_ate || faixa.numero_patrimonial_de,
          bens: itens,
        })
      }
      state.faixasAntigas = []
      persist(state, controls)
      render(state, controls)
    } catch (error) {
      setError(controls, error instanceof Error ? error.message : 'Não foi possível restaurar os bens.')
    } finally {
      setBusy(state, controls, false)
    }
  }

  function getControls(root) {
    return {
      root,
      hidden: root.querySelector('input[type="hidden"]'),
      origem: document.getElementById('id_unidade_administrativa_origem'),
      geral: root.querySelector('.movimentacao-lote__criterio--geral'),
      faixa: root.querySelector('.movimentacao-lote__criterio--faixa'),
      termo: root.querySelector('.movimentacao-lote__termo'),
      de: root.querySelector('[id$="-busca-de"]'),
      ate: root.querySelector('[id$="-busca-ate"]'),
      pesquisar: root.querySelector('.movimentacao-lote__pesquisar'),
      importar: root.querySelector('.movimentacao-lote__importar'),
      resultados: root.querySelector('.movimentacao-lote__resultados tbody'),
      selecionarResultados: root.querySelector('.movimentacao-lote__selecionar-resultados'),
      selecionados: root.querySelector('.movimentacao-lote__selecionados tbody'),
      tituloSelecionados: root.querySelector('.movimentacao-lote__selecionados-titulo'),
      vazio: root.querySelector('.movimentacao-lote__vazio'),
      erro: root.querySelector('.movimentacao-lote__erro'),
      mais: root.querySelector('.movimentacao-lote__mais'),
      resolverUrl: root.dataset.resolverUrl,
      pesquisarUrl: root.dataset.pesquisarUrl,
    }
  }

  function bindEvents(state, controls) {
    controls.root.querySelectorAll('input[name$="-modo"]').forEach((radio) => {
      radio.addEventListener('change', () => changeMode(state, controls, radio.value))
    })
    controls.termo.addEventListener('input', () => resetResults(state, controls))
    ;[controls.de, controls.ate].forEach((input) => {
      input.addEventListener('input', () => {
        input.value = formatarNumeroPatrimonial(input.value)
        resetResults(state, controls)
      })
    })
    controls.pesquisar.addEventListener('click', () => void pesquisarBens(state, controls))
    controls.importar.addEventListener('click', () => void importarFaixa(state, controls))
    controls.mais.addEventListener('click', () => void pesquisarBens(state, controls, state.proximaPagina))
    controls.selecionarResultados.addEventListener('change', () => toggleVisibleResults(state, controls))
    controls.origem.addEventListener('change', () => {
      state.versao += 1
      state.selecoes = []
      state.modo = 'geral'
      controls.root.querySelector('input[value="geral"]').checked = true
      resetResults(state, controls)
      setModeLayout(state, controls)
    })
    controls.root.closest('form')?.addEventListener('submit', (event) => {
      if (!state.busy) return
      event.preventDefault()
      setError(controls, 'Aguarde a busca de bens terminar antes de salvar.')
    })
  }

  function initialize(root) {
    const controls = getControls(root)
    if (Object.values(controls).some((control) => !control)) return
    const state = createInitialState(controls.hidden)
    bindEvents(state, controls)
    controls.root.querySelector(`input[value="${state.modo}"]`).checked = true
    setModeLayout(state, controls)
    if (state.faixasAntigas.length) void restoreLegacyRanges(state, controls)
  }

  function initializeWidgets() {
    document.querySelectorAll('.movimentacao-lote').forEach(initialize)
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeWidgets)
  } else {
    initializeWidgets()
  }
})()
