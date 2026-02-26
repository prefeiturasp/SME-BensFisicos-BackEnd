(function () {
    function ready(fn) {
        if (document.readyState !== 'loading') fn()
        else document.addEventListener('DOMContentLoaded', fn)
    }

    function ensurePrefixEl(afterEl) {
        const prefixId = 'uo-prefixo-codigo';
        const existing = document.getElementById(prefixId);
        if (existing) return existing;

        const el = document.createElement('span');
        el.id = prefixId;
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
        const uo = document.getElementById('id_unidade_orcamentaria');
        const sufixo = document.getElementById('id_codigo_sufixo');

        if (!uo || !sufixo) return;

        const prefixEl = ensurePrefixEl(sufixo);

        function setPrefix() {
            const selected = uo.options[uo.selectedIndex];
            if (!selected?.value) {
                prefixEl.textContent = '—';
                return;
            }
            const txt = (selected.textContent || '').trim();
            const codigo = txt.split(' - ')[0].trim();
            prefixEl.textContent = codigo ? (codigo + '.') : '—';
        }

        setPrefix()
        uo.addEventListener('change', function () {
            setPrefix()
        })
    })
})()