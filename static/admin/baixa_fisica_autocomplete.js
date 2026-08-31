(function() {
    function startWhenReady() {
        if (!window.django || !django.jQuery) {
            return setTimeout(startWhenReady, 100);
        }

        const $ = django.jQuery;

        $(function() {
            const $uaSelect = $('#id_unidade_administrativa_origem'); // criação
            const $uaReadonlyLink = $('.form-row.field-unidade_administrativa_origem .readonly a'); // edição

            // status em modo readonly na edição
            const $statusReadonly = $('.form-row.field-status .readonly');
            const isEdicao = $statusReadonly.length > 0;

            function getUaVal() {
                // criação: usa o select normalmente
                if ($uaSelect.length) {
                    return $uaSelect.val() || '';
                }

                // edição: extrai o ID do href
                if ($uaReadonlyLink.length) {
                    const href = $uaReadonlyLink.attr('href') || '';
                    // ex: /admin/dados_comuns/unidadeadministrativa/109/change/
                    const match = href.match(/unidadeadministrativa\/(\d+)\/change\/?/);
                    if (match?.[1]) {
                        return match[1];
                    }
                }
                return '';
            }

            function getAddButton() {
                let $btn = $('#baixafisicabensitem_set-group .add-row a, #baixafisicabensitem_set-group .add-row');
                if (!$btn.length) {
                    $btn = $('.inline-group .add-row a, .inline-group .add-row');
                }
                return $btn;
            }

            function isStatusAguardandoEnvio() {
                if (!isEdicao) return false;
                const txt = ($statusReadonly.text() || '').trim().toLowerCase();
                return txt === 'aguardando envio' || txt === 'em elaboração' || txt === 'em elaboracao';
            }

            function enableAdd($addButton) {
                $addButton.removeClass('disabled');
                $addButton.css({
                    'pointer-events': 'auto',
                    'opacity': '1'
                });
                $('select[name^="itens-"][name$="-bem"]').prop('disabled', false);
            }

            function disableAdd($addButton) {
                $addButton.addClass('disabled');
                $addButton.css({
                    'pointer-events': 'none',
                    'opacity': '0.4'
                });
                $('select[name^="itens-"][name$="-bem"]').prop('disabled', true);
            }

            function toggleAddButton() {
                const $addButton = getAddButton();

                if (!$addButton.length) {
                    // backend não renderizou botão (status != aguardando_envio)
                    return;
                }

                // EDIÇÃO
                if (isEdicao) {
                    if (isStatusAguardandoEnvio() && getUaVal()) {
                        enableAdd($addButton);
                    } else {
                        disableAdd($addButton);
                    }
                    return;
                }

                // CRIAÇÃO
                const uaVal = getUaVal();
                if (uaVal) {
                    enableAdd($addButton);
                } else {
                    disableAdd($addButton);
                }
            }

            // roda ao carregar
            toggleAddButton();

            // só na criação existe select; na edição, não tem change
            $uaSelect.on('change', toggleAddButton);

            // --- Filtro no autocomplete dos bens ---
            const oldAjax = $.ajax;

            function appendBemIdIfNotDeleted(ids, selectEl) {
                const prefix = selectEl.name.replace('-bem', '');
                const deleteFlag = $('input[name="' + prefix + '-DELETE"]').prop('checked');
                if (!deleteFlag) {
                    const val = $(selectEl).val();
                    if (val) {
                        ids.push(val);
                    }
                }
            }

            $.ajax = function wrapAjaxWithUaFilter(options) {
                const isStringUrl = typeof options === 'string';
                const opts = isStringUrl ? options : { ...options };
                const url = isStringUrl ? opts : opts.url;

                if (!url || url.indexOf('/admin/autocomplete/') === -1) {
                    return oldAjax.apply(this, arguments);
                }

                const uaVal = getUaVal();
                if (!uaVal) {
                    return oldAjax.apply(this, arguments);
                }
                const params = ['ua_origem=' + encodeURIComponent(uaVal)];
                const ids = [];
                const selects = document.querySelectorAll('select[name^="itens-"][name$="-bem"]');
                for (const selectEl of selects) {
                    appendBemIdIfNotDeleted(ids, selectEl);
                }
                if (ids.length > 0) {
                    params.push('exclude_bens=' + encodeURIComponent(ids.join(',')));
                }

                if (params.length) {
                    const sep = url.indexOf('?') === -1 ? '?' : '&';
                    const newUrl = url + sep + params.join('&');
                    return oldAjax.apply(this, [isStringUrl ? newUrl : { ...opts, url: newUrl }]);
                }
                return oldAjax.apply(this, [opts]);
            };
        });
    }

    startWhenReady();
})();