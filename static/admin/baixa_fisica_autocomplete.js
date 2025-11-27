(function() {
    function startWhenReady() {
        if (!window.django || !django.jQuery) {
            return setTimeout(startWhenReady, 100);
        }

        var $ = django.jQuery;

        $(function() {
            var $uaSelect = $('#id_unidade_administrativa_origem'); // criação
            var $uaReadonlyLink = $('.form-row.field-unidade_administrativa_origem .readonly a'); // edição

            // status em modo readonly na edição
            var $statusReadonly = $('.form-row.field-status .readonly');
            var isEdicao = $statusReadonly.length > 0;

            function getUaVal() {
                // criação: usa o select normalmente
                if ($uaSelect.length) {
                    return $uaSelect.val() || '';
                }

                // edição: extrai o ID do href
                if ($uaReadonlyLink.length) {
                    var href = $uaReadonlyLink.attr('href') || '';
                    // ex: /admin/dados_comuns/unidadeadministrativa/109/change/
                    var match = href.match(/unidadeadministrativa\/(\d+)\/change\/?/);
                    if (match && match[1]) {
                        return match[1];
                    }
                }
                return '';
            }

            function getAddButton() {
                var $btn = $('#baixafisicabensitem_set-group .add-row a, #baixafisicabensitem_set-group .add-row');
                if (!$btn.length) {
                    $btn = $('.inline-group .add-row a, .inline-group .add-row');
                }
                return $btn;
            }

            function isStatusAguardandoEnvio() {
                if (!isEdicao) return false;
                var txt = ($statusReadonly.text() || '').trim().toLowerCase();
                return txt === 'aguardando envio';
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
                var $addButton = getAddButton();

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
                var uaVal = getUaVal();
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
            var oldAjax = $.ajax;
            $.ajax = function(options) {
                var opts = options;
                var url = (typeof opts === 'string') ? opts : opts.url;

                if (!url || url.indexOf('/admin/autocomplete/') === -1) {
                    return oldAjax.apply(this, arguments);
                }

                var params = [];
                var uaVal = getUaVal();

                if (!uaVal) {
                    return oldAjax.apply(this, arguments);
                }

                params.push('ua_origem=' + encodeURIComponent(uaVal));

                var ids = [];
                $('select[name^="itens-"][name$="-bem"]').each(function() {
                    var prefix = this.name.replace('-bem','');
                    var deleteFlag = $('input[name="' + prefix + '-DELETE"]').prop('checked');
                    if (!deleteFlag) {
                        var val = $(this).val();
                        if (val) ids.push(val);
                    }
                });

                if (ids.length > 0) {
                    params.push('exclude_bens=' + encodeURIComponent(ids.join(',')));
                }

                if (params.length) {
                    var sep = url.indexOf('?') === -1 ? '?' : '&';
                    url = url + sep + params.join('&');
                    if (typeof opts === 'string') {
                        opts = url;
                    } else {
                        opts.url = url;
                    }
                }

                return oldAjax.apply(this, [opts]);
            };
        });
    }

    startWhenReady();
})();