(function () {
  function getCsrfToken() {
    return document.cookie
      .split('; ')
      .find((cookie) => cookie.startsWith('csrftoken='))
      ?.split('=')[1]
  }

  function initialize(root) {
    const hidden = root.querySelector('input[type="hidden"]')
    const origem = document.getElementById('id_unidade_administrativa_origem')
    const de = root.querySelector('[id$="-de"]')
    const ate = root.querySelector('[id$="-ate"]')
    const adicionar = root.querySelector('.movimentacao-lote__adicionar')
    const selecionarTodos = root.querySelector('.movimentacao-lote__selecionar-todos')
    const resumo = root.querySelector('.movimentacao-lote__resumo tbody')
    const erro = root.querySelector('.movimentacao-lote__erro')
    const opcoes = root.querySelector('.movimentacao-lote__opcoes')
    const url = root.dataset.resolverUrl
    const buscarUrl = root.dataset.buscarUrl
    if (!hidden || !origem || !de || !ate || !adicionar || !selecionarTodos || !resumo || !erro || !opcoes || !url || !buscarUrl) return

    const state = { faixas: [], selecionar_todos: false, todos: [] }

    function setError(message) {
      erro.textContent = message || ''
    }

    function persist() {
      hidden.value = JSON.stringify({
        faixas: state.faixas.map(({ numero_patrimonial_de, numero_patrimonial_ate }) => ({
          numero_patrimonial_de,
          ...(numero_patrimonial_ate ? { numero_patrimonial_ate } : {}),
        })),
        selecionar_todos: state.selecionar_todos,
      })
    }

    function render() {
      resumo.replaceChildren()
      const rows = state.selecionar_todos
        ? [{ titulo: 'Todos os Bens aprovados da UA de origem', nomes: `${state.todos.length} bem(ns) selecionado(s)`, all: true }]
        : state.faixas.map((faixa) => ({
            titulo: faixa.numero_patrimonial_ate
              ? `${faixa.numero_patrimonial_de} até ${faixa.numero_patrimonial_ate}`
              : faixa.numero_patrimonial_de,
            nomes: faixa.itens.map((item) => item.nome).join(', '),
            faixa,
          }))
      rows.forEach((row) => {
        const tr = document.createElement('tr')
        const remover = document.createElement('button')
        remover.type = 'button'
        remover.className = 'button'
        remover.textContent = 'Excluir'
        remover.addEventListener('click', () => {
          if (row.all) {
            state.selecionar_todos = false
            state.todos = []
            selecionarTodos.checked = false
          } else {
            state.faixas = state.faixas.filter((faixa) => faixa !== row.faixa)
          }
          persist()
          render()
        })
        const cells = [row.titulo, row.nomes]
        cells.forEach((text) => {
          const td = document.createElement('td')
          td.textContent = text
          tr.appendChild(td)
        })
        const action = document.createElement('td')
        action.appendChild(remover)
        tr.appendChild(action)
        resumo.appendChild(tr)
      })
      de.disabled = state.selecionar_todos
      ate.disabled = state.selecionar_todos
      adicionar.disabled = state.selecionar_todos
      root.classList.toggle('movimentacao-lote--todos', state.selecionar_todos)
    }

    async function resolver(payload) {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrfToken() || '' },
        body: JSON.stringify({ unidade_administrativa_origem: origem.value, ...payload }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Não foi possível incluir os bens.')
      return body.itens
    }

    async function carregarOpcoes(input) {
      if (!origem.value) return
      const params = new URLSearchParams({
        unidade_administrativa_origem: origem.value,
        q: input.value.trim(),
      })
      const response = await fetch(`${buscarUrl}?${params.toString()}`)
      if (!response.ok) return
      const body = await response.json()
      opcoes.replaceChildren()
      body.itens.forEach((item) => {
        const itemLista = document.createElement('li')
        const option = document.createElement('button')
        option.type = 'button'
        option.textContent = `${item.numero_patrimonial} - ${item.nome}`
        option.addEventListener('click', () => {
          input.value = item.numero_patrimonial
          opcoes.hidden = true
        })
        itemLista.appendChild(option)
        opcoes.appendChild(itemLista)
      })
      opcoes.hidden = body.itens.length === 0
    }

    adicionar.addEventListener('click', async () => {
      if (!origem.value || !de.value.trim()) {
        setError('Informe a Unidade Administrativa de origem e o Número Patrimonial - De.')
        return
      }
      setError('')
      try {
        const faixa = {
          numero_patrimonial_de: de.value.trim(),
          numero_patrimonial_ate: ate.value.trim(),
        }
        const itens = await resolver({ faixas: [faixa] })
        const ids = new Set(state.faixas.flatMap((item) => item.itens.map((bem) => bem.id)))
        if (itens.some((item) => ids.has(item.id))) {
          throw new Error('Os bens informados já foram adicionados à movimentação.')
        }
        state.faixas.push({ ...faixa, itens })
        de.value = ''
        ate.value = ''
        persist()
        render()
      } catch (error) {
        setError(error instanceof Error ? error.message : 'Não foi possível incluir os bens.')
      }
    })

    selecionarTodos.addEventListener('change', async () => {
      if (!selecionarTodos.checked) {
        state.selecionar_todos = false
        state.todos = []
        persist()
        render()
        return
      }
      if (!origem.value) {
        selecionarTodos.checked = false
        setError('Informe a Unidade Administrativa de origem.')
        return
      }
      setError('')
      try {
        state.todos = await resolver({ selecionar_todos: true })
        state.faixas = []
        state.selecionar_todos = true
        persist()
        render()
      } catch (error) {
        selecionarTodos.checked = false
        setError(error instanceof Error ? error.message : 'Não foi possível incluir os bens.')
      }
    })

    const camposNumero = [de, ate]
    camposNumero.forEach((input) => {
      input.addEventListener('focus', () => void carregarOpcoes(input))
      input.addEventListener('input', () => void carregarOpcoes(input))
      input.addEventListener('blur', () => {
        window.setTimeout(() => {
          opcoes.hidden = true
        }, 150)
      })
    })

    origem.addEventListener('change', () => {
      state.faixas = []
      state.todos = []
      state.selecionar_todos = false
      selecionarTodos.checked = false
      persist()
      render()
    })
    persist()
    render()
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.movimentacao-lote').forEach(initialize)
  })
})()
