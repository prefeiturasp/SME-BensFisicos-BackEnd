(function () {
  'use strict'

  const state = {
    allowExit: false,
    forceDirty: false,
    initialSnapshot: null,
    pendingUrl: null,
  }

  const dialogCopy = {
    create: {
      title: 'Sair sem salvar?',
      message: 'As informações preenchidas ainda não foram salvas. Se você sair agora, elas serão perdidas.',
      confirmLabel: 'Descartar e sair',
      cancelLabel: 'Continuar preenchendo',
    },
    edit: {
      title: 'Descartar alterações?',
      message: 'As alterações realizadas ainda não foram salvas. Se você sair agora, elas serão perdidas.',
      confirmLabel: 'Descartar alterações',
      cancelLabel: 'Continuar editando',
    },
    selection: {
      title: 'Descartar seleção?',
      message: 'Os itens selecionados ainda não foram utilizados. Se você sair agora, a seleção será perdida.',
      confirmLabel: 'Descartar seleção',
      cancelLabel: 'Manter seleção',
    },
  }

  function getMode(form) {
    if (form.id === 'changelist-form') return 'selection'
    return globalThis.location.pathname.endsWith('/add/') ? 'create' : 'edit'
  }

  function getDialogCopy(form) {
    const mode = getMode(form)
    return dialogCopy[mode]
  }

  function hasSelectedRows(form) {
    return Boolean(form.querySelector('input.action-select:checked'))
  }

  function findChangeForm() {
    return document.querySelector('#content-main form[id$="_form"]')
      || document.querySelector('#content-main form[method="post"]')
  }

  function serializeValue(value) {
    if (value instanceof File) {
      if (!value.name && value.size === 0) return null
      return `file:${value.name}:${value.size}:${value.lastModified}`
    }
    return String(value)
  }

  function snapshotForm(form) {
    const values = []
    for (const [name, value] of new FormData(form).entries()) {
      if (name === 'csrfmiddlewaretoken' || name.startsWith('_')) continue
      const serializedValue = serializeValue(value)
      if (serializedValue !== null) values.push([name, serializedValue])
    }
    return JSON.stringify(values)
  }

  function formHasErrors(form) {
    const errors = form.querySelectorAll('.errorlist, .errornote')
    return Array.from(errors).some(function (element) {
      return !element.classList.contains('hide') && Boolean(element.textContent.trim())
    })
  }

  function hasUnsavedChanges(form) {
    if (getMode(form) === 'selection') return hasSelectedRows(form)
    if (state.initialSnapshot === null) return false
    return state.forceDirty || snapshotForm(form) !== state.initialSnapshot
  }

  function createButton(label, className) {
    const button = document.createElement('button')
    button.type = 'button'
    button.className = `button ${className}`
    button.textContent = label
    return button
  }

  function createDialog(copy) {
    const dialog = document.createElement('dialog')
    dialog.className = 'unsaved-changes-dialog'
    dialog.setAttribute('aria-labelledby', 'unsaved-changes-title')

    const content = document.createElement('div')
    content.className = 'unsaved-changes-dialog__content'

    const title = document.createElement('h2')
    title.id = 'unsaved-changes-title'
    title.className = 'unsaved-changes-dialog__title'
    title.textContent = copy.title

    const message = document.createElement('p')
    message.className = 'unsaved-changes-dialog__message'
    message.textContent = copy.message

    const actions = document.createElement('div')
    actions.className = 'unsaved-changes-dialog__actions'
    const continueButton = createButton(
      copy.cancelLabel,
      'unsaved-changes-dialog__continue',
    )
    const discardButton = createButton(
      copy.confirmLabel,
      'unsaved-changes-dialog__discard',
    )

    actions.append(continueButton, discardButton)
    content.append(title, message, actions)
    dialog.append(content)
    document.body.append(dialog)

    return { dialog, continueButton, discardButton }
  }

  function closeDialog(dialog) {
    state.pendingUrl = null
    dialog.close()
  }

  function bindDialogActions(controls) {
    controls.continueButton.addEventListener('click', function () {
      closeDialog(controls.dialog)
    })
    controls.dialog.addEventListener('cancel', function (event) {
      event.preventDefault()
      closeDialog(controls.dialog)
    })
    controls.discardButton.addEventListener('click', function () {
      const destination = state.pendingUrl
      state.allowExit = true
      state.pendingUrl = null
      controls.dialog.close()
      if (destination) globalThis.location.assign(destination)
    })
  }

  function findChangelistUrl() {
    const links = document.querySelectorAll('div.breadcrumbs a[href]')
    return links.length ? links[links.length - 1].href : null
  }

  function addCancelLink() {
    const submitRow = document.querySelector('.submit-row')
    const destination = findChangelistUrl()
    if (!submitRow || !destination || submitRow.querySelector('.unsaved-changes-cancel')) return

    const link = document.createElement('a')
    link.href = destination
    link.className = 'button closelink unsaved-changes-cancel'
    link.textContent = 'Cancelar'
    submitRow.append(link)
  }

  function shouldIgnoreLink(event, link) {
    if (event.defaultPrevented || event.button !== 0) return true
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return true
    if (link.target === '_blank' || link.hasAttribute('download')) return true
    const destination = new URL(link.href, globalThis.location.href)
    return destination.href === globalThis.location.href
      || (destination.pathname === globalThis.location.pathname
        && destination.search === globalThis.location.search
        && Boolean(destination.hash))
  }

  function bindNavigationProtection(form, controls) {
    document.addEventListener('click', function (event) {
      if (!(event.target instanceof Element)) return
      const link = event.target.closest('a[href]')
      if (!link || shouldIgnoreLink(event, link)) return
      if (state.allowExit || !hasUnsavedChanges(form)) return

      event.preventDefault()
      state.pendingUrl = link.href
      if (!controls.dialog.open) controls.dialog.showModal()
    })

    globalThis.addEventListener('beforeunload', function (event) {
      if (state.allowExit || !hasUnsavedChanges(form)) return
      event.preventDefault()
    })
  }

  function bindSuccessfulSubmit(form) {
    form.addEventListener('submit', function (event) {
      queueMicrotask(function () {
        if (!event.defaultPrevented) state.allowExit = true
      })
    })
  }

  function captureInitialState(form) {
    globalThis.setTimeout(function () {
      state.forceDirty = formHasErrors(form)
      state.initialSnapshot = snapshotForm(form)
    }, 0)
  }

  function initialize() {
    const form = findChangeForm()
    if (!form) return

    addCancelLink()
    const controls = createDialog(getDialogCopy(form))
    bindDialogActions(controls)
    bindNavigationProtection(form, controls)
    bindSuccessfulSubmit(form)
    captureInitialState(form)
  }

  document.addEventListener('DOMContentLoaded', initialize)
})()
