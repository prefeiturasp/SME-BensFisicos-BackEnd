(function() {
    function criarOpcao(item, selected) {
        return new Option(item.label, item.id, false, selected);
    }

    function limparSelect(selectEl) {
        while (selectEl.options.length > 0) {
            selectEl.remove(0);
        }
    }

    function garantirCaixaErro(jq, $uoField) {
        const targetId = 'movimentacao-uo-destino-error';
        let $error = jq('#' + targetId);
        if ($error.length) {
            return $error;
        }

        $error = jq('<ul/>', {
            id: targetId,
            class: 'errorlist',
            css: { display: 'none' }
        });

        $uoField.closest('.form-row, .field-unidade_orcamentaria_destino').append($error);
        return $error;
    }

    function atualizarDestino(jq, $uoField, $uaField, config, $error) {
        const uoSelecionada = String($uoField.val() || '');
        const uoReferencia = String(config.uoReferenciaId || '');
        const centraisPorUo = config.centraisPorUo || {};
        const opcoesMesmaUo = Array.isArray(config.opcoesMesmaUo) ? config.opcoesMesmaUo : [];
        const valorAtual = String($uaField.val() || '');
        const selectEl = $uaField.get(0);

        limparSelect(selectEl);
        selectEl.add(criarOpcao({ id: '', label: '---------' }, false));
        $error.empty().hide();

        if (!uoSelecionada) {
            $uaField.prop('disabled', true).val('');
            return;
        }

        if (uoReferencia && uoSelecionada === uoReferencia) {
            opcoesMesmaUo.forEach(function(item) {
                const selected = valorAtual && String(item.id) === valorAtual;
                selectEl.add(criarOpcao(item, selected));
            });
            $uaField.prop('disabled', false);
            if (valorAtual) {
                $uaField.val(valorAtual);
            }
            return;
        }

        const central = centraisPorUo[uoSelecionada];
        if (!central) {
            $uaField.prop('disabled', true).val('');
            $error.append(jq('<li/>').text(config.mensagemSemPontoCentral || ''));
            $error.show();
            return;
        }

        selectEl.add(criarOpcao(central, true));
        $uaField.prop('disabled', true).val(String(central.id));
    }

    function init() {
        if (!window.django || !django.jQuery) {
            return setTimeout(init, 100);
        }

        const jq = django.jQuery;

        jq(function() {
            const $uoField = jq('#id_unidade_orcamentaria_destino');
            const $uaField = jq('#id_unidade_administrativa_destino');

            if (!$uoField.length || !$uaField.length) {
                return;
            }

            const rawConfig = $uoField.attr('data-movimentacao-destino-config');
            if (!rawConfig) {
                return;
            }

            let config = null;
            try {
                config = JSON.parse(rawConfig);
            } catch (error) {
                console.error('Falha ao ler configuracao de destino da movimentacao.', error);
                return;
            }

            const $error = garantirCaixaErro(jq, $uoField);

            atualizarDestino(jq, $uoField, $uaField, config, $error);
            $uoField.on('change', function() {
                atualizarDestino(jq, $uoField, $uaField, config, $error);
            });
        });
    }

    init();
})();