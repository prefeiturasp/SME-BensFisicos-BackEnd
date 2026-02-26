(function() {
    const $ = window.django?.jQuery;

    function wrapAjaxWithUaFilter(jq, oldAjax, $ua) {
        return function(options) {
            const isStringUrl = typeof options === 'string';
            const opts = isStringUrl ? options : { ...options };
            const url = isStringUrl ? opts : opts.url;

            if (!url || url.indexOf('/admin/autocomplete/') === -1) {
                return oldAjax.apply(this, arguments);
            }

            const params = [];
            const uaVal = $ua.val();
            if (uaVal) {
                params.push('ua_origem=' + encodeURIComponent(uaVal));
            }

            const ids = [];
            jq('select[name^="itens-"][name$="-bem"]').each(function() {
                const prefix = this.name.replace('-bem', '');
                const deleteFlag = jq('input[name="' + prefix + '-DELETE"]').prop('checked');
                if (!deleteFlag) {
                    const val = jq(this).val();
                    if (val) ids.push(val);
                }
            });
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
    }

    function startWhenReady() {
        if (!window.django || !django.jQuery) {
            return setTimeout(startWhenReady, 100);
        }

        const jq = django.jQuery;
        jq(function() {
            const $ua = jq('#id_unidade_administrativa_origem');
            const oldAjax = jq.ajax;
            jq.ajax = wrapAjaxWithUaFilter(jq, oldAjax, $ua);
        });
    }

    startWhenReady();
})();