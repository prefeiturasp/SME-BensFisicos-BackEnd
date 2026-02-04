(function () {
    function ready(fn) {
        if (document.readyState !== 'loading') fn()
        else document.addEventListener('DOMContentLoaded', fn)
    }

    function ensurePrefixEl(afterEl) {
        var id = 'uo-prefixo-codigo'
        var existing = document.getElementById(id)
        if (existing) return existing

        var el = document.createElement('span')
        el.id = id
        el.style.display = 'inline-block'
        el.style.padding = '6px 10px'
        el.style.marginRight = '8px'
        el.style.border = '1px solid #d1d5db'
        el.style.borderRadius = '6px'
        el.style.background = '#f9fafb'
        el.style.fontFamily = 'monospace'
        el.style.fontSize = '12px'
        el.textContent = '—'

        
        afterEl.parentNode.insertBefore(el, afterEl)
        return el
    }

    ready(function () {
        var uo = document.getElementById('id_unidade_orcamentaria')
        var sufixo = document.getElementById('id_codigo_sufixo')

        if (!uo || !sufixo) return

        var prefixEl = ensurePrefixEl(sufixo)

        function setPrefix() {
            var selected = uo.options[uo.selectedIndex]
            if (!selected || !selected.value) {
                prefixEl.textContent = '—'
                return
            }

            
            var txt = (selected.textContent || '').trim()
            var codigo = txt.split(' - ')[0].trim()
            prefixEl.textContent = codigo ? (codigo + '.') : '—'
        }

        setPrefix()
        uo.addEventListener('change', function () {
            setPrefix()
        })
    })
})()