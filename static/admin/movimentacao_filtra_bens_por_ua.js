(function() {
    function startWhenReady() {
        if (!window.django || !django.jQuery) {
            return setTimeout(startWhenReady, 100);
        }

        var $ = django.jQuery;

        $(function() {
            var $ua = $('#id_unidade_administrativa_origem');
            var oldAjax = $.ajax;

            $.ajax = function(options) {
                var opts = options;
                var url = (typeof opts === 'string') ? opts : opts.url;

                if (!url || url.indexOf('/admin/autocomplete/') === -1) {
                    return oldAjax.apply(this, arguments);
                }

                var params = [];

                // -------------------------
                // UA de origem
                // -------------------------
                var uaVal = $ua.val();
                if (uaVal) {
                    params.push('ua_origem=' + encodeURIComponent(uaVal));
                }

                // -------------------------
                // EXCLUIR BENS JÁ ESCOLHIDOS
                // (sempre mandamos; o backend decide se usa)
                // -------------------------
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
                    params.push(
                        'exclude_bens=' + encodeURIComponent(ids.join(','))
                    );
                }

                // -------------------------
                // ANEXA OS PARAMS NA URL
                // -------------------------
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