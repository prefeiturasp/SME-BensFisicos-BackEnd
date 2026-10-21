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

  function getSavedSummary(saved, mode) {
    if (Array.isArray(saved.resumo)) return saved.resumo
    return saved.resumos_por_modo?.[mode] || []
  }

  function getSavedItemIds(saved, summary) {
    if (Array.isArray(saved.itens)) return new Set(saved.itens)
    return new Set(summary.map((bem) => bem.id))
  }

  function restoreSavedState(state, saved) {
    state.faixasAntigas = Array.isArray(saved.faixas) ? saved.faixas : []
    if (['geral', 'faixa', 'visualizar', 'todos'].includes(saved.modo)) state.modo = saved.modo
    if (Array.isArray(saved.selecoes)) {
      state.selecoes = saved.selecoes
      return
    }

    const summary = getSavedSummary(saved, state.modo)
    if (saved.selecionar_todos && summary.length) {
      state.selecoes = [{ id: 'todos', tipo: 'todos', bens: summary }]
      return
    }

    const ids = getSavedItemIds(saved, summary)
    state.selecoes = summary.filter((bem) => ids.has(bem.id))
      .map((bem) => ({ id: `bem-${bem.id}`, tipo: 'individual', bens: [bem] }))
  }

  function createInitialState(hidden) {
    const state = {
      modo: 'geral', selecoes: [], resultados: [], proximaPagina: null,
      total: 0, faixasAntigas: [], versao: 0, busy: false, busyVersion: 0,
      autocompleteTimer: null, autocompleteVersion: 0,
    }
    try {
      const saved = JSON.parse(hidden.value || '{}')
      restoreSavedState(state, saved)
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
    return values.map((value) => {
      const cell = document.createElement('td')
      cell.textContent = value
      row.appendChild(cell)
      return cell
    })
  }

  function createHelp(message) {
    const help = document.createElement('span')
    help.className = 'movimentacao-lote__ajuda'
    help.tabIndex = 0
    help.textContent = '?'
    help.setAttribute('role', 'img')
    help.setAttribute('aria-label', message)
    return help
  }

  function manualMode(state) {
    return state.modo === 'geral' || state.modo === 'visualizar'
  }

  function goodsTable(bens) {
    const table = document.createElement('table')
    const header = table.createTHead().insertRow()
    for (const title of ['Número Patrimonial', 'Nome do Bem']) {
      const cell = document.createElement('th')
      cell.textContent = title
      header.appendChild(cell)
    }
    const body = table.createTBody()
    for (const bem of bens) appendCells(body.insertRow(), [bem.numero_patrimonial || 'Sem número patrimonial', bem.nome || '-'])
    return table
  }

  function openDialog(controls, title, content, confirmLabel, onConfirm, cancelLabel = 'Cancelar', variant = 'primary') {
    const dialog = document.createElement('dialog')
    dialog.className = 'admin-confirm-dialog movimentacao-lote__dialog'
    dialog.setAttribute('aria-label', title)
    const container = document.createElement('div')
    container.className = 'admin-confirm-dialog__content'
    const heading = document.createElement('h2')
    heading.className = 'admin-confirm-dialog__title'
    heading.textContent = title
    heading.tabIndex = -1
    heading.setAttribute('autofocus', '')
    content.classList.add('admin-confirm-dialog__message')
    const body = document.createElement('div')
    body.className = 'admin-confirm-dialog__body'
    body.appendChild(content)
    const footer = document.createElement('div')
    footer.className = 'admin-confirm-dialog__footer'
    const error = document.createElement('p')
    error.className = 'movimentacao-lote__erro'
    error.setAttribute('role', 'alert')
    const actions = document.createElement('div')
    actions.className = 'admin-confirm-dialog__actions'
    const cancel = document.createElement('button')
    cancel.type = 'button'
    cancel.className = 'button admin-confirm-dialog__cancel'
    cancel.textContent = cancelLabel
    const confirm = document.createElement('button')
    confirm.type = 'button'
    confirm.className = variant === 'destructive' ? 'button admin-confirm-dialog__discard' : 'button default'
    confirm.textContent = confirmLabel
    let pending = false
    cancel.addEventListener('click', () => dialog.close())
    dialog.addEventListener('cancel', (event) => { if (pending) event.preventDefault() })
    dialog.addEventListener('close', () => dialog.remove())
    confirm.addEventListener('click', async () => {
      if (pending) return
      pending = true
      error.textContent = ''
      dialog.querySelectorAll('button, input').forEach((input) => { input.disabled = true })
      try {
        await onConfirm()
        dialog.close()
      } catch (requestError) {
        error.textContent = requestError instanceof Error ? requestError.message : 'Não foi possível concluir. Tente novamente.'
      } finally {
        pending = false
        dialog.querySelectorAll('button, input').forEach((input) => { input.disabled = false })
      }
    })
    actions.append(cancel, confirm)
    footer.append(error, actions)
    container.append(heading, body, footer)
    dialog.appendChild(container)
    controls.root.appendChild(dialog)
    dialog.showModal()
    return dialog
  }

  function bindHelpTooltips(controls) {
    const tooltip = document.createElement('div')
    tooltip.id = `${controls.hidden.id}-ajuda-tooltip`
    tooltip.className = 'movimentacao-lote__tooltip'
    tooltip.setAttribute('role', 'tooltip')
    tooltip.hidden = true
    document.body.appendChild(tooltip)
    let activeHelp = null

    function hideHelp() {
      activeHelp?.removeAttribute('aria-describedby')
      activeHelp = null
      tooltip.hidden = true
    }

    function showHelp(event) {
      const help = event.target.closest('.movimentacao-lote__ajuda')
      if (!help || help === activeHelp) return
      hideHelp()
      activeHelp = help
      ;(help.closest('dialog') || document.body).appendChild(tooltip)
      tooltip.textContent = help.getAttribute('aria-label')
      tooltip.hidden = false
      help.setAttribute('aria-describedby', tooltip.id)
      const anchor = help.getBoundingClientRect()
      const bounds = tooltip.getBoundingClientRect()
      const left = Math.max(8, Math.min(anchor.left, globalThis.innerWidth - bounds.width - 8))
      const top = anchor.top >= bounds.height + 8
        ? anchor.top - bounds.height - 8 : anchor.bottom + 8
      tooltip.style.left = `${left}px`
      tooltip.style.top = `${top}px`
    }

    function dismissHelp(event) {
      if (!activeHelp?.contains(event.relatedTarget)) hideHelp()
    }

    controls.root.addEventListener('mouseover', showHelp)
    controls.root.addEventListener('focusin', showHelp)
    controls.root.addEventListener('mouseout', dismissHelp)
    controls.root.addEventListener('focusout', dismissHelp)
    controls.root.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') hideHelp()
    })
    globalThis.addEventListener('scroll', hideHelp, true)
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
    const disabled = bem.apto === false || blocked.has(bem.id)
    if (disabled) {
      row.className = 'movimentacao-lote__bloqueado'
      row.setAttribute('aria-disabled', 'true')
    }
    if (manualMode(state)) {
      const cell = document.createElement('td')
      const checkbox = document.createElement('input')
      checkbox.type = 'checkbox'
      checkbox.checked = selected.has(bem.id)
      checkbox.disabled = state.busy || disabled
      checkbox.setAttribute('aria-label', `Selecionar bem ID ${bem.id}`)
      checkbox.addEventListener('change', () => toggleIndividual(state, controls, bem, checkbox.checked))
      cell.appendChild(checkbox)
      row.appendChild(cell)
    }
    const situation = bem.apto !== false && blocked.has(bem.id)
      ? 'Já incluído em uma faixa selecionada'
      : bem.motivo || 'Apto para movimentação'
    const cells = appendCells(row, [bem.id, bem.numero_patrimonial || 'Sem número patrimonial', bem.nome || '-',
      bem.descricao || '-', bem.localizacao || '-'])
    if (!bem.numero_patrimonial?.trim()) {
      cells[1].append(' ', createHelp('Este bem está cadastrado sem número patrimonial. Sua seleção segue as mesmas regras de movimentação dos demais bens; a ausência do número, por si só, não impede a movimentação.'))
    }
    const situationCell = document.createElement('td')
    situationCell.textContent = situation
    row.appendChild(situationCell)
    if (disabled) {
      const message = bem.apto !== false && blocked.has(bem.id)
        ? 'Este bem pertence a uma faixa selecionada e não pode ser desmarcado individualmente. Para retirá-lo, remova ou edite a faixa da lista de selecionados.'
        : bem.motivo || 'Este bem não está apto para movimentação.'
      const help = document.createElement('span')
      help.className = 'movimentacao-lote__ajuda'
      help.tabIndex = 0
      help.textContent = '!'
      help.setAttribute('role', 'img')
      help.setAttribute('aria-label', message)
      const text = document.createElement('span')
      text.className = 'movimentacao-lote__situacao-texto'
      text.textContent = situation
      const summary = document.createElement('span')
      summary.className = 'movimentacao-lote__situacao'
      summary.title = message
      summary.append(text, help)
      situationCell.replaceChildren(summary)
    }
    return row
  }

  function selectionLabel(selection) {
    if (selection.tipo === 'todos') return 'Todos os bens aptos da UA de origem'
    if (selection.tipo === 'faixa') {
      return selection.numeroAte && selection.numeroAte !== selection.numeroDe
        ? `${selection.numeroDe} até ${selection.numeroAte}` : selection.numeroDe
    }
    const bem = selection.bens[0]
    return bem.numero_patrimonial || 'Sem número patrimonial'
  }

  function createSelectionRow(selection, state, controls, readOnly = false) {
    const row = document.createElement('tr')
    const names = selection.bens.slice(0, 2).map((bem) => bem.nome || '-').join(', ')
    const suffix = selection.bens.length > 2 ? ` e mais ${selection.bens.length - 2}` : ''
    const displayNames = readOnly ? selection.bens.map((bem) => bem.nome || '-').join(', ') : names + suffix
    const cells = appendCells(row, [selectionLabel(selection), selection.bens.length, displayNames])
    if (selection.tipo === 'faixa') {
      const hint = document.createElement('small')
      hint.className = 'movimentacao-lote__faixa-resumo'
      hint.textContent = 'Faixa completa · seleção em conjunto'
      cells[0].appendChild(hint)
    }
    if (readOnly) return row
    const action = document.createElement('td')
    if (selection.tipo === 'faixa') {
      const edit = document.createElement('button')
      edit.type = 'button'
      edit.disabled = state.busy
      edit.title = 'Ver/editar faixa'
      edit.className = 'button movimentacao-lote__editar'
      edit.appendChild(actionIcon(controls.root.dataset.editIcon))
      edit.setAttribute('aria-label', `Ver/editar faixa ${selectionLabel(selection)}`)
      edit.addEventListener('click', () => editRange(state, controls, selection))
      action.appendChild(edit)
    }
    const remove = document.createElement('button')
    remove.type = 'button'
    remove.className = 'button movimentacao-lote__remover'
    remove.title = 'Remover seleção'
    remove.appendChild(actionIcon(controls.root.dataset.removeIcon))
    remove.disabled = state.busy
    remove.setAttribute('aria-label', `Remover seleção ${selectionLabel(selection)}`)
    remove.addEventListener('click', () => confirmRemoval(selection, state, controls))
    action.appendChild(remove)
    row.appendChild(action)
    return row
  }

  function selectionTable(selections) {
    if (selections.length === 1 && selections[0].tipo === 'todos') {
      const table = goodsTable(selections[0].bens)
      const caption = table.createCaption()
      caption.append('Todos os bens aptos da UA de origem ', createHelp('Todos os bens aptos da UA de origem serão incluídos na movimentação. Para marcar ou desmarcar bens específicos, volte para Seleção manual.'))
      return table
    }
    const table = document.createElement('table')
    const header = table.createTHead().insertRow()
    for (const title of ['Número Patrimonial', 'Quantidade', 'Nome do Bem']) {
      const cell = document.createElement('th')
      cell.textContent = title
      header.appendChild(cell)
    }
    const body = table.createTBody()
    for (const selection of selections) body.appendChild(createSelectionRow(selection, null, null, true))
    return table
  }

  function actionIcon(url) {
    const icon = document.createElement('img')
    icon.src = url
    icon.alt = ''
    icon.width = 16
    icon.height = 16
    return icon
  }

  function confirmRemoval(selection, state, controls) {
    const content = document.createElement('p')
    content.textContent = `Deseja remover ${selectionLabel(selection)} da movimentação? Os cadastros dos bens não serão apagados.`
    const version = state.versao
    openDialog(controls, 'Remover seleção?', content, 'Remover da seleção', () => {
      if (version !== state.versao) throw new Error('A seleção foi alterada. Tente novamente.')
      state.selecoes = state.selecoes.filter((item) => item.id !== selection.id)
      persist(state, controls)
      render(state, controls)
    }, 'Voltar', 'destructive')
  }

  function updateHeaderCheckbox(state, controls) {
    const selected = selectionIds(state.selecoes)
    const blocked = blockedIds(state.selecoes)
    const selectable = manualMode(state)
      ? state.resultados.filter((bem) => bem.apto !== false && !blocked.has(bem.id)) : []
    const selectedCount = selectable.filter((bem) => selected.has(bem.id)).length
    controls.selecionarResultados.disabled = state.busy || !selectable.length
    controls.selecionarResultados.checked = selectable.length > 0 && selectedCount === selectable.length
    controls.selecionarResultados.indeterminate = selectedCount > 0 && selectedCount < selectable.length
  }

  function render(state, controls) {
    controls.colunaSelecao.hidden = !manualMode(state)
    controls.resultados.closest('.movimentacao-lote__tabelas').hidden = state.modo === 'todos' || !state.resultados.length
    controls.tituloResultados.hidden = state.modo === 'todos' || !state.resultados.length
    controls.tituloResultados.textContent = `Resultados da Busca (${state.total})`
    controls.resultados.replaceChildren(...state.resultados.map((bem) => createResultRow(bem, state, controls)))
    controls.tituloSelecionados.textContent = `Selecionados (${selectionIds(state.selecoes).size})`
    controls.tituloSelecionados.hidden = !state.selecoes.length
    controls.selecionados.closest('.movimentacao-lote__tabelas').hidden = !state.selecoes.length
    const automatic = state.modo === 'todos'
    controls.selecionados.closest('table').hidden = automatic
    controls.automaticos.hidden = !automatic || !state.selecoes.length
    if (automatic) {
      controls.automaticos.replaceChildren(selectionTable(state.selecoes))
    }
    if (state.selecoes.length && !automatic) {
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
    controls.mais.hidden = state.modo === 'todos' || !state.proximaPagina
    controls.importar.hidden = state.modo !== 'faixa' || state.total === 0
    controls.ajudaImportar.hidden = controls.importar.hidden
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

  function hideAutocomplete(controls) {
    controls.opcoes.hidden = true
  }

  function showAutocomplete(options, input) {
    const rect = input.getBoundingClientRect()
    const below = globalThis.innerHeight - rect.bottom - 12
    const above = rect.top - 12
    const openBelow = below >= 160 || below >= above
    options.style.left = `${Math.max(8, rect.left)}px`
    options.style.width = `${Math.min(rect.width, globalThis.innerWidth - Math.max(8, rect.left) - 8)}px`
    options.style.top = openBelow ? `${rect.bottom + 4}px` : 'auto'
    options.style.bottom = openBelow ? 'auto' : `${globalThis.innerHeight - rect.top + 4}px`
    options.style.maxHeight = `${Math.max(0, Math.min(240, openBelow ? below : above))}px`
    options.hidden = options.childElementCount === 0
  }

  function cancelAutocomplete(state, controls) {
    if (state.autocompleteTimer) globalThis.clearTimeout(state.autocompleteTimer)
    state.autocompleteTimer = null
    state.autocompleteVersion += 1
    if (controls) hideAutocomplete(controls)
  }

  function createAutocompleteOption(item, input, onSelect) {
    const listItem = document.createElement('li')
    const button = document.createElement('button')
    button.type = 'button'
    button.textContent = `${item.numero_patrimonial} - ${item.nome}`
    button.setAttribute('aria-label', `Selecionar ${item.numero_patrimonial}`)
    button.addEventListener('mousedown', (event) => event.preventDefault())
    button.addEventListener('click', () => {
      input.value = item.numero_patrimonial
      onSelect()
    })
    listItem.appendChild(button)
    return listItem
  }

  async function loadAutocompleteOptions(state, controls, input) {
    if (!controls.origem.value || state.modo !== 'faixa') return
    const version = ++state.autocompleteVersion
    const params = new URLSearchParams({
      unidade_administrativa_origem: controls.origem.value,
      q: input.value.trim(),
    })
    try {
      const response = await fetch(`${controls.buscarUrl}?${params}`)
      if (!response.ok || version !== state.autocompleteVersion) return
      const body = await response.json()
      if (version !== state.autocompleteVersion) return
      controls.opcoes.replaceChildren(
        ...body.itens.map((item) => createAutocompleteOption(item, input, () => {
          cancelAutocomplete(state, controls)
          resetResults(state, controls)
        })),
      )
      showAutocomplete(controls.opcoes, input)
    } catch {
      if (version === state.autocompleteVersion) hideAutocomplete(controls)
    }
  }

  function scheduleAutocomplete(state, controls, input) {
    cancelAutocomplete(state)
    state.autocompleteTimer = globalThis.setTimeout(() => {
      state.autocompleteTimer = null
      void loadAutocompleteOptions(state, controls, input)
    }, 300)
  }

  function setModeLayout(state, controls) {
    controls.abas.hidden = state.modo === 'todos'
    controls.abas.querySelectorAll('[role="tab"]').forEach((tab) => {
      tab.setAttribute('aria-selected', String(tab.dataset.modo === state.modo))
    })
    controls.root.querySelector('input[value="manual"]').checked = state.modo !== 'todos'
    controls.root.querySelector('input[value="todos"]').checked = state.modo === 'todos'
    controls.geral.hidden = state.modo !== 'geral'
    controls.faixa.hidden = state.modo !== 'faixa'
    controls.visualizar.hidden = state.modo !== 'visualizar'
    controls.pesquisar.hidden = ['todos', 'visualizar'].includes(state.modo)
    controls.importar.hidden = state.modo !== 'faixa' || state.total === 0
    controls.ajudaImportar.hidden = state.modo !== 'faixa' || state.total === 0
    controls.vazio.textContent = ''
    setError(controls, '')
    persist(state, controls)
    render(state, controls)
  }

  function searchParams(state, controls, page) {
    const params = new URLSearchParams({ unidade_administrativa_origem: controls.origem.value, pagina: page })
    if (manualMode(state)) {
      const term = controls.termo.value.trim()
      if (state.modo === 'geral' && term) params.set('termo_busca', term)
      return params
    }
    const start = controls.de.value.trim()
    const end = controls.ate.value.trim()
    if (!start || (end && start.split('-')[0] > end.split('-')[0])) {
      throw new Error('Informe um intervalo válido: o Número Patrimonial Até deve ser maior ou igual ao De.')
    }
    params.set('numero_patrimonial_de', start)
    if (end) params.set('numero_patrimonial_ate', end)
    return params
  }

  function setBusy(state, controls, busy) {
    state.busyVersion += 1
    state.busy = busy
    controls.pesquisar.disabled = busy
    controls.importar.disabled = busy
    controls.mais.disabled = busy
    controls.selecionarResultados.disabled = busy
    controls.root.querySelectorAll('input[name$="-modo"]').forEach((radio) => { radio.disabled = busy })
    controls.abas.querySelectorAll('[role="tab"]').forEach((tab) => { tab.disabled = busy })
    render(state, controls)
    return state.busyVersion
  }

  function finishRequest(state, controls, request) {
    // Only the request owning the busy state can release the controls.
    if (request === state.busyVersion) setBusy(state, controls, false)
  }

  async function pesquisarBens(state, controls, page = 1) {
    if (state.busy) return
    cancelAutocomplete(state, controls)
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
    if (state.modo === 'faixa') {
      state.resultados = []
      state.total = 0
      render(state, controls)
    }
    const request = setBusy(state, controls, true)
    setError(controls, '')
    try {
      const body = await searchResults(state, controls, params)
      if (versao !== state.versao) return
      state.resultados = page === 1 ? body.itens : [...state.resultados, ...body.itens]
      state.proximaPagina = body.proxima_pagina
      state.total = body.count
      controls.vazio.textContent = body.count ? '' : 'A busca não retornou resultados.'
      render(state, controls)
    } catch (error) {
      if (versao === state.versao) {
        setError(controls, error instanceof Error ? error.message : 'Não foi possível buscar bens.')
      }
    } finally {
      finishRequest(state, controls, request)
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

  function rangePayload(de, ate) {
    const start = de.trim()
    const end = ate.trim()
    if (!start) throw new Error('Informe o Número Patrimonial - De.')
    if (end && start.split('-')[0] > end.split('-')[0]) {
      throw new Error('O Número Patrimonial Até deve ser maior ou igual ao Número Patrimonial De.')
    }
    return { numero_patrimonial_de: start, ...(end ? { numero_patrimonial_ate: end } : {}) }
  }

  async function searchResults(state, controls, params) {
    if (state.modo === 'faixa') {
      const faixa = rangePayload(controls.de.value, controls.ate.value)
      const itens = await resolver(controls, { faixas: [faixa] })
      if (!itens.length) throw new Error('Nenhum bem apto foi encontrado na faixa informada.')
      return { itens, count: itens.length, proxima_pagina: null }
    }
    const response = await fetch(`${controls.pesquisarUrl}?${params}`)
    const body = await response.json()
    if (!response.ok) throw new Error(body.detail || 'Não foi possível buscar bens.')
    return body
  }

  function rangeInput(id, label, value, help) {
    const container = document.createElement('div')
    container.className = 'movimentacao-lote__criterio'
    const title = document.createElement('label')
    title.htmlFor = id
    title.textContent = label
    const labelRow = document.createElement('div')
    labelRow.className = 'movimentacao-lote__rotulo'
    labelRow.appendChild(title)
    labelRow.append(' ', createHelp(help))
    const input = document.createElement('input')
    input.type = 'text'
    input.id = id
    input.value = value
    input.inputMode = 'numeric'
    input.maxLength = 15
    input.placeholder = '000.000000000-0'
    input.addEventListener('input', () => { input.value = formatarNumeroPatrimonial(input.value) })
    container.append(labelRow, input)
    return { container, input }
  }

  function editRange(state, controls, selection) {
    const content = document.createElement('div')
    const description = document.createElement('p')
    description.textContent = 'Altere De/Até para substituir a faixa. A sequência e a disponibilidade dos bens serão validadas ao aplicar. Os bens não podem ser removidos individualmente.'
    const ajudaDe = controls.de.previousElementSibling.querySelector('[aria-label]').getAttribute('aria-label')
    const ajudaAte = controls.ate.previousElementSibling.querySelector('[aria-label]').getAttribute('aria-label')
    const de = rangeInput(`${controls.hidden.id}-editar-de`, 'Número Patrimonial - De', selection.numeroDe, ajudaDe)
    const ate = rangeInput(`${controls.hidden.id}-editar-ate`, 'Número Patrimonial - Até', selection.numeroAte, ajudaAte)
    const fields = document.createElement('div')
    fields.className = 'movimentacao-lote__criterio--faixa'
    fields.append(de.container, ate.container)
    const count = document.createElement('p')
    count.textContent = `Bens da faixa após aplicar (${selection.bens.length})`
    count.setAttribute('role', 'status')
    const help = document.createElement('p')
    help.append('Como buscar por faixa ', createHelp(controls.ajudaFaixa.getAttribute('aria-label')))
    const preview = document.createElement('div')
    preview.appendChild(rangePreviewTable(selection.bens, selection.bens))
    const notice = document.createElement('p')
    notice.setAttribute('role', 'status')
    content.append(description, fields, help, count, notice, preview)
    const version = state.versao
    async function validate() {
      const faixa = rangePayload(de.input.value, ate.input.value)
      const itens = await resolver(controls, { faixas: [faixa] })
      if (version !== state.versao) throw new Error('A seleção foi alterada. Abra a faixa novamente.')
      if (!itens.length) throw new Error('Nenhum bem apto foi encontrado na faixa informada.')
      const others = selectionIds(state.selecoes.filter((item) => item.id !== selection.id))
      if (itens.some((bem) => others.has(bem.id))) throw new Error('Um ou mais bens da faixa já foram adicionados à movimentação.')
      return { faixa, itens }
    }
    const dialog = openDialog(controls, 'Ver/editar faixa', content, 'Aplicar faixa', async () => {
      const { faixa, itens } = await validate()
      const numeroDe = faixa.numero_patrimonial_de
      const numeroAte = faixa.numero_patrimonial_ate || numeroDe
      const updated = { id: `faixa-${numeroDe}-${numeroAte}`, tipo: 'faixa', numeroDe, numeroAte, bens: itens }
      state.selecoes = state.selecoes.map((item) => item.id === selection.id ? updated : item)
      persist(state, controls)
      render(state, controls)
    })
    bindRangePreview(dialog, [de.input, ate.input], selection, validate, preview, count, notice)
    bindEditAutocomplete(dialog, de, controls)
    bindEditAutocomplete(dialog, ate, controls)
  }

  function rangePreviewTable(original, target) {
    const previous = new Set(original.map((bem) => bem.id))
    const next = new Set(target?.map((bem) => bem.id))
    const rows = (target === null ? [...original] : [...target, ...original.filter((bem) => !next.has(bem.id))])
      .sort((a, b) => (a.numero_patrimonial || '').localeCompare(b.numero_patrimonial || '', 'pt-BR', { numeric: true }))
    const table = goodsTable(rows)
    const header = document.createElement('th')
    header.append('Situação ', createHelp('Esta lista é uma prévia das alterações na faixa. Os bens novos serão incluídos, os mantidos continuarão na faixa e os indicados para remoção sairão dela. A seleção só será alterada ao clicar em "Aplicar faixa".'))
    table.tHead.rows[0].appendChild(header)
    rows.forEach((bem, index) => {
      let status = 'mantido'
      let label = 'Mantido'
      if (target === null) { label = 'Seleção atual' }
      else if (!next.has(bem.id)) { status = 'removido'; label = 'Será removido' }
      else if (!previous.has(bem.id)) { status = 'novo'; label = 'Novo' }
      const row = table.tBodies[0].rows[index]
      row.className = `movimentacao-lote__previa--${status}`
      appendCells(row, [label])
    })
    return table
  }

  function bindRangePreview(dialog, inputs, selection, validate, preview, count, notice) {
    let timer
    let version = 0
    async function update(request) {
      try {
        const { itens } = await validate()
        if (request !== version || !dialog.open) return
        preview.replaceChildren(rangePreviewTable(selection.bens, itens))
        count.textContent = `Bens da faixa após aplicar (${itens.length})`
        notice.textContent = ''
        notice.setAttribute('role', 'status')
      } catch (error) {
        if (request !== version || !dialog.open) return
        notice.textContent = `${error.message} A seleção atual permanece inalterada.`
        notice.setAttribute('role', 'alert')
      }
    }
    function schedule() {
      const request = ++version
      globalThis.clearTimeout(timer)
      notice.setAttribute('role', 'status')
      preview.replaceChildren(rangePreviewTable(selection.bens, null))
      count.textContent = `Bens da faixa atual (${selection.bens.length})`
      notice.textContent = 'Atualizando prévia...'
      if (inputs[0].value === selection.numeroDe && inputs[1].value === selection.numeroAte) {
        preview.replaceChildren(rangePreviewTable(selection.bens, selection.bens))
        count.textContent = `Bens da faixa após aplicar (${selection.bens.length})`
        notice.textContent = ''
        return
      }
      timer = globalThis.setTimeout(() => void update(request), 350)
    }
    for (const input of inputs) input.addEventListener('input', schedule)
    dialog.addEventListener('close', () => { version += 1; globalThis.clearTimeout(timer) })
  }

  function bindEditAutocomplete(dialog, field, controls) {
    const options = document.createElement('ul')
    options.id = `${field.input.id}-opcoes`
    options.className = 'movimentacao-lote__opcoes'
    options.hidden = true
    field.input.setAttribute('autocomplete', 'off')
    field.container.appendChild(options)
    let timer
    let version = 0
    async function load(request) {
      const params = new URLSearchParams({
        unidade_administrativa_origem: controls.origem.value, q: field.input.value.trim(),
      })
      try {
        const response = await fetch(`${controls.buscarUrl}?${params}`)
        if (!response.ok) return
        const body = await response.json()
        if (request !== version || !dialog.open) return
        const items = body.itens.filter((bem) => bem.numero_patrimonial)
        options.replaceChildren(...items.map((bem) => createAutocompleteOption(bem, field.input, () => {
          field.input.dispatchEvent(new Event('input', { bubbles: true }))
          dismiss()
        })))
        showAutocomplete(options, field.input)
      } catch {
        if (request === version) dismiss()
      }
    }
    function schedule() {
      dismiss()
      const request = version
      options.replaceChildren()
      timer = globalThis.setTimeout(() => void load(request), 300)
    }
    function dismiss() {
      version += 1
      globalThis.clearTimeout(timer)
      options.hidden = true
    }
    field.input.addEventListener('input', schedule)
    field.input.addEventListener('focus', schedule)
    field.input.addEventListener('blur', (event) => {
      if (!options.contains(event.relatedTarget)) dismiss()
    })
    options.addEventListener('focusout', (event) => {
      if (!options.contains(event.relatedTarget)) dismiss()
    })
    function hideOnScroll(event) {
      if (!options.hidden && !options.contains(event.target)) dismiss()
    }
    globalThis.addEventListener('scroll', hideOnScroll, true)
    globalThis.addEventListener('resize', dismiss)
    dialog.addEventListener('close', () => {
      dismiss()
      globalThis.removeEventListener('scroll', hideOnScroll, true)
      globalThis.removeEventListener('resize', dismiss)
    })
  }

  async function importarFaixa(state, controls) {
    if (state.busy) return
    cancelAutocomplete(state, controls)
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
    const request = setBusy(state, controls, true)
    setError(controls, '')
    const version = state.versao
    try {
      const itens = await resolver(controls, {
        faixas: [{
          numero_patrimonial_de: numeroDe,
          ...(numeroAteInformado ? { numero_patrimonial_ate: numeroAteInformado } : {}),
        }],
      })
      if (version !== state.versao) return
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
      if (version === state.versao) {
        setError(controls, error instanceof Error ? error.message : 'Não foi possível importar a faixa.')
      }
    } finally {
      finishRequest(state, controls, request)
    }
  }

  async function selecionarTodos(state, controls) {
    if (!controls.origem.value) {
      throw new Error('Informe a Unidade Administrativa de origem.')
    }
    const versao = ++state.versao
    const request = setBusy(state, controls, true)
    setError(controls, '')
    try {
      const itens = await resolver(controls, { selecionar_todos: true })
      if (versao !== state.versao) return
      if (!itens.length) throw new Error('Nenhum bem aprovado foi encontrado na unidade administrativa de origem.')
      state.selecoes = [{ id: 'todos', tipo: 'todos', bens: itens }]
      state.modo = 'todos'
      resetResults(state, controls)
      setModeLayout(state, controls)
    } catch (error) {
      if (versao === state.versao) throw error
    } finally {
      finishRequest(state, controls, request)
    }
  }

  function changeMode(state, controls, newMode) {
    if (state.busy) return
    if (newMode === 'todos') {
      setModeLayout(state, controls)
      cancelAutocomplete(state, controls)
      if (state.selecoes.length) {
        const content = document.createElement('div')
        const message = document.createElement('p')
        message.textContent = 'A seleção abaixo será descartada e substituída por todos os bens aptos da UA de origem.'
        content.append(message, selectionTable(state.selecoes))
        openDialog(controls, 'Descartar seleção?', content, 'Descartar selecionados',
          () => selecionarTodos(state, controls), 'Voltar', 'destructive')
      } else {
        void selecionarTodos(state, controls).catch((error) => setError(controls, error.message))
      }
      return
    }
    cancelAutocomplete(state, controls)
    const previousMode = state.modo
    const sairDaSelecaoDeTodos = previousMode === 'todos' && newMode !== 'todos'
    state.modo = newMode
    if (sairDaSelecaoDeTodos) {
      state.selecoes = []
    }
    resetResults(state, controls)
    setModeLayout(state, controls)
    if (newMode === 'visualizar') void pesquisarBens(state, controls)
  }

  function toggleVisibleResults(state, controls) {
    if (!manualMode(state) || state.busy) return
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
    const version = state.versao
    const request = setBusy(state, controls, true)
    try {
      for (const [index, faixa] of state.faixasAntigas.entries()) {
        const itens = await resolver(controls, { faixas: [faixa] })
        if (version !== state.versao) return
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
      if (version === state.versao) {
        setError(controls, error instanceof Error ? error.message : 'Não foi possível restaurar os bens.')
      }
    } finally {
      finishRequest(state, controls, request)
    }
  }

  function getControls(root) {
    const automaticos = document.createElement('div')
    automaticos.className = 'movimentacao-lote__automaticos'
    automaticos.hidden = true
    root.querySelector('.movimentacao-lote__selecionados').after(automaticos)
    return {
      root,
      automaticos,
      hidden: root.querySelector('input[type="hidden"]'),
      origem: document.getElementById('id_unidade_administrativa_origem'),
      geral: root.querySelector('.movimentacao-lote__criterio--geral'),
      faixa: root.querySelector('.movimentacao-lote__criterio--faixa'),
      visualizar: root.querySelector('.movimentacao-lote__visualizar'),
      ajudaFaixa: root.querySelector('.movimentacao-lote__ajuda-faixa .movimentacao-lote__ajuda'),
      abas: root.querySelector('.movimentacao-lote__abas'),
      ajudaImportar: root.querySelector('.movimentacao-lote__ajuda-importar'),
      colunaSelecao: root.querySelector('.movimentacao-lote__coluna-selecao'),
      termo: root.querySelector('.movimentacao-lote__termo'),
      de: root.querySelector('[id$="-busca-de"]'),
      ate: root.querySelector('[id$="-busca-ate"]'),
      opcoes: root.querySelector('.movimentacao-lote__opcoes'),
      pesquisar: root.querySelector('.movimentacao-lote__pesquisar'),
      importar: root.querySelector('.movimentacao-lote__importar'),
      resultados: root.querySelector('.movimentacao-lote__resultados tbody'),
      tituloResultados: root.querySelector('.movimentacao-lote__resultados-titulo'),
      selecionarResultados: root.querySelector('.movimentacao-lote__selecionar-resultados'),
      selecionados: root.querySelector('.movimentacao-lote__selecionados tbody'),
      tituloSelecionados: root.querySelector('.movimentacao-lote__selecionados-titulo'),
      vazio: root.querySelector('.movimentacao-lote__vazio'),
      erro: root.querySelector('.movimentacao-lote__erro'),
      mais: root.querySelector('.movimentacao-lote__mais'),
      resolverUrl: root.dataset.resolverUrl,
      buscarUrl: root.dataset.buscarUrl,
      pesquisarUrl: root.dataset.pesquisarUrl,
    }
  }

  function bindModeRadio(state, controls, radio) {
    radio.addEventListener('change', () => changeMode(state, controls, radio.value === 'manual' ? 'geral' : 'todos'))
  }

  function bindRangeInput(state, controls, input) {
    input.addEventListener('focus', () => void loadAutocompleteOptions(state, controls, input))
    input.addEventListener('input', () => {
      input.value = formatarNumeroPatrimonial(input.value)
      resetResults(state, controls)
      scheduleAutocomplete(state, controls, input)
    })
    input.addEventListener('blur', (event) => {
      if (!controls.opcoes.contains(event.relatedTarget)) hideAutocomplete(controls)
    })
  }

  function bindEvents(state, controls) {
    globalThis.addEventListener('scroll', (event) => {
      if (!controls.opcoes.hidden && !controls.opcoes.contains(event.target)) cancelAutocomplete(state, controls)
    }, true)
    globalThis.addEventListener('resize', () => cancelAutocomplete(state, controls))
    controls.opcoes.addEventListener('focusout', (event) => {
      if (!controls.opcoes.contains(event.relatedTarget)) hideAutocomplete(controls)
    })
    controls.root.querySelectorAll('input[name$="-modo"]')
      .forEach((radio) => bindModeRadio(state, controls, radio))
    controls.abas.querySelectorAll('[role="tab"]').forEach((tab) => {
      tab.addEventListener('click', () => changeMode(state, controls, tab.dataset.modo))
    })
    controls.termo.addEventListener('input', () => resetResults(state, controls))
    ;[controls.de, controls.ate].forEach((input) => bindRangeInput(state, controls, input))
    controls.pesquisar.addEventListener('click', () => void pesquisarBens(state, controls))
    controls.importar.addEventListener('click', () => void importarFaixa(state, controls))
    controls.mais.addEventListener('click', () => void pesquisarBens(state, controls, state.proximaPagina))
    controls.selecionarResultados.addEventListener('change', () => toggleVisibleResults(state, controls))
    controls.origem.addEventListener('change', () => {
      cancelAutocomplete(state, controls)
      state.versao += 1
      state.selecoes = []
      state.busy = false
      state.modo = 'geral'
      controls.root.querySelector('dialog')?.close()
      resetResults(state, controls)
      setModeLayout(state, controls)
      setBusy(state, controls, false)
    })
    controls.root.closest('form')?.addEventListener('submit', (event) => reviewSubmit(event, state, controls), true)
  }

  function selectedLabel(id) {
    const field = document.getElementById(id)
    return field?.selectedOptions?.[0]?.textContent || field?.value || 'Não informado'
  }

  function validateReviewDestination() {
    const destination = document.getElementById('id_unidade_administrativa_destino')
    document.getElementById('movimentacao-checkout-destino-error')?.remove()
    if (destination?.value) return true

    const field = destination?.disabled
      ? document.getElementById('id_unidade_orcamentaria_destino')
      : destination
    const error = document.createElement('ul')
    error.id = 'movimentacao-checkout-destino-error'
    error.className = 'errorlist'
    error.setAttribute('role', 'alert')
    const message = document.createElement('li')
    message.textContent = 'Selecione a unidade administrativa de destino antes de revisar a movimentação.'
    error.appendChild(message)
    field?.closest('.form-row')?.appendChild(error)
    field?.scrollIntoView({ block: 'center' })
    field?.focus()
    return false
  }

  function reviewSubmit(event, state, controls) {
    if (state.confirmedSubmit) return
    event.preventDefault()
    event.stopImmediatePropagation()
    if (state.busy) {
      setError(controls, 'Aguarde a busca de bens terminar antes de salvar.')
      return
    }
    if (controls.root.querySelector('dialog[open]')) return
    if (!validateReviewDestination()) return
    if (!state.selecoes.length) {
      setError(controls, 'Adicione ao menos um item de movimentação.')
      controls.root.scrollIntoView({ block: 'center' })
      return
    }
    const content = document.createElement('div')
    for (const [label, id] of [
      ['Origem', 'id_unidade_administrativa_origem'],
      ['UO de destino', 'id_unidade_orcamentaria_destino'],
      ['UA de destino', 'id_unidade_administrativa_destino'],
    ]) {
      const line = document.createElement('p')
      line.textContent = `${label}: ${selectedLabel(id)}`
      content.appendChild(line)
    }
    const observation = document.createElement('p')
    observation.textContent = `Observação: ${document.getElementById('id_observacao')?.value || 'Não informada'}`
    const count = document.createElement('p')
    count.textContent = `Selecionados (${selectionIds(state.selecoes).size})`
    content.append(observation, count, selectionTable(state.selecoes))
    const form = event.target
    const submitter = event.submitter
    openDialog(controls, 'Revisar e salvar movimentação', content, 'Salvar movimentação', () => {
      persist(state, controls)
      form.querySelector('[data-movimentacao-submit]')?.remove()
      if (submitter?.name) {
        const action = document.createElement('input')
        action.type = 'hidden'
        action.name = submitter.name
        action.value = submitter.value
        action.dataset.movimentacaoSubmit = 'true'
        form.appendChild(action)
      }
      state.confirmedSubmit = true
      try {
        if (submitter) form.requestSubmit(submitter)
        else form.requestSubmit()
      } finally {
        state.confirmedSubmit = false
      }
    }, 'Voltar para editar')
  }

  function initialize(root) {
    const controls = getControls(root)
    if (Object.values(controls).some((control) => !control)) return
    const state = createInitialState(controls.hidden)
    bindHelpTooltips(controls)
    bindEvents(state, controls)
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
