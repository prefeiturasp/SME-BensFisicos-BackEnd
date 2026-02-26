(function () {
    function ready(fn) {
        if (document.readyState !== 'loading') fn()
        else document.addEventListener('DOMContentLoaded', fn)
    }

    function setSelected(selectEl, value) {
        if (!selectEl) return;
        for (let i = 0; i < selectEl.options.length; i++) {
            if (selectEl.options[i].value === value) {
                selectEl.selectedIndex = i;
                return;
            }
        }
    }

    ready(function () {
        const uo = document.getElementById('id_unidade_orcamentaria');
        const ua = document.getElementById('id_unidade_administrativa');

        if (!uo || !ua) return;

        const url = new URL(window.location.href);
        const uoParam = url.searchParams.get('unidade_orcamentaria');
        if (uoParam) {
            setSelected(uo, uoParam);
        }

        if (uo.disabled) return;

        uo.addEventListener('change', function () {
            const uoId = uo.value || '';
            ua.value = '';
            const newUrl = new URL(window.location.href);

            if (uoId) {
                newUrl.searchParams.set('unidade_orcamentaria', uoId);
            } else {
                newUrl.searchParams.delete('unidade_orcamentaria');
            }

            window.location.href = newUrl.toString();
        });
    });
})()