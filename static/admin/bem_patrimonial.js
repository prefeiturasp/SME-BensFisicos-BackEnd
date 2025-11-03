// static/admin/bem_patrimonial.js
(function(){
  function id(s){ return document.getElementById(s); }
  function qs(s, r){ return (r || document).querySelector(s); }
  function qsa(s, r){ return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function onlyDigits(s){ return (s||'').replace(/\D/g,''); }
  function fmt(d){
    d = (d||'').slice(0,13);
    var p1=d.slice(0,3), p2=d.slice(3,12), p3=d.slice(12,13);
    if (d.length <= 3) return p1;
    if (d.length <= 12) return p1 + '.' + p2;
    return p1 + '.' + p2 + '-' + p3;
  }

  function formatBRMoneyFromDigits(digits){
    if (!digits) digits = "0";
    digits = digits.replace(/^0+/, "") || "0";
    if (digits.length === 1) digits = "0" + digits;
    if (digits.length === 2) digits = "0" + digits;
    var cents = digits.slice(-2);
    var ints  = digits.slice(0, -2);
    var withThousand = ints.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return withThousand + "," + cents;
  }

  function bindCurrencyMask(){
    var el = id("id_valor_unitario");
    if (!el || el.dataset.boundMask === "1") return;
    el.dataset.boundMask = "1";
    (function init(){
      var raw = (el.value || "").trim();
      if (raw && !/^\d{1,3}(\.\d{3})*,\d{2}$/.test(raw)){
        var digits = raw.replace(/[^\d]/g, "");
        el.value = formatBRMoneyFromDigits(digits);
      }
    })();
    el.addEventListener("input", function(){
      var digits = (el.value || "").replace(/[^\d]/g, "");
      el.value = formatBRMoneyFromDigits(digits);
    });
    el.addEventListener("blur", function(){
      var digits = (el.value || "").replace(/[^\d]/g, "");
      el.value = formatBRMoneyFromDigits(digits);
    });
    el.setAttribute("required", "required");
  }

  function bindSingleNumeroPatrimonialMask(){
    var np   = id('id_numero_patrimonial');
    var ant  = id('id_numero_formato_antigo');
    var sem  = id('id_sem_numeracao');
    var isEdit = !id('id_cadastro_modo'); // add tem o rádio; edit não tem
    if (!np || !ant) return;

    function setReadOnly(on){
      if (on){ np.setAttribute('readonly','readonly'); np.setAttribute('aria-readonly','true'); }
      else { np.removeAttribute('readonly'); np.removeAttribute('aria-readonly'); }
    }

    function refresh(){
      var semAtivo = !!(sem && sem.checked && !isEdit);
      if (semAtivo){
        np.value = '';
        setReadOnly(true);
        np.removeAttribute('pattern');
        np.placeholder = 'Gerado automaticamente';
        if (ant){ ant.disabled = true; ant.checked = false; }
        return;
      } else {
        setReadOnly(false);
        if (ant) ant.disabled = false;
      }
      if (ant && ant.checked){
        np.removeAttribute('pattern');
        np.placeholder = 'Valor livre (formato antigo)';
      } else {
        np.setAttribute('pattern', '^\\d{3}\\.\\d{9}-\\d$');
        np.value = fmt(onlyDigits(np.value));
        np.placeholder = '000.000000000-0';
      }
    }

    if (ant) ant.addEventListener('change', refresh);
    if (sem) sem.addEventListener('change', refresh);
    np.addEventListener('input', function(){
      var semAtivo = !!(sem && sem.checked && !isEdit);
      if (!(ant && ant.checked) && !semAtivo){
        np.value = fmt(onlyDigits(np.value));
      }
    });
    refresh();
  }

  // ---------- MULTI UI ----------
  function multiHTML(){
    return [
      '<div id="base-required-errors" class="errornote hide" style="margin-bottom:8px;"></div>',
      '<div id="multi-container" class="multi-inline hide">',
      '  <div class="multi-head">Múltiplos Bens</div>',
      '  <div class="multi-help">Adicione linhas com Número Patrimonial (ou marque "Sem numeração" / "Formato antigo") e a Localização específica. As mesmas validações do formulário padrão se aplicam por linha.</div>',
      '  <div id="multi-errors" class="errornote hide" style="margin-bottom:8px;"></div>',
      '  <div id="multi-rows"></div>',
      '  <button type="button" class="button" id="multi-add">+ Adicionar linha</button>',
      '  <input type="hidden" id="id_multi_payload" name="multi_payload" value="">',
      '</div>'
    ].join('');
  }

  function rowTemplate(idx){
    return [
      '<div class="multi-row" data-idx="', idx, '">',
      '  <div>',
      '    <label>Nº Patrimonial</label>',
      '    <input type="text" class="vTextField fld-npat" placeholder="000.000000000-0">',
      '  </div>',
      '  <div>',
      '    <label><input type="checkbox" class="fld-ant"> Formato antigo</label>',
      '  </div>',
      '  <div>',
      '    <label><input type="checkbox" class="fld-sem"> Sem numeração</label>',
      '  </div>',
      '  <div>',
      '    <label>Localização</label>',
      '    <input type="text" class="vTextField fld-loc">',
      '  </div>',
      '  <div>',
      '    <button type="button" class="button rm">Remover</button>',
      '  </div>',
      '</div>'
    ].join('');
  }

  function toPayload(){
    var rows = qsa('#multi-rows .multi-row');
    var out = [];
    rows.forEach(function(r){
      out.push({
        numero_patrimonial: (qs('.fld-npat', r).value || '').trim(),
        numero_formato_antigo: !!qs('.fld-ant', r).checked,
        sem_numeracao: !!qs('.fld-sem', r).checked,
        localizacao: (qs('.fld-loc', r).value || '').trim()
      });
    });
    var hidden = id('id_multi_payload');
    if (hidden) hidden.value = JSON.stringify(out);
  }

  function applyMask(row){
    var input = qs('.fld-npat', row);
    var ant = qs('.fld-ant', row);
    var sem = qs('.fld-sem', row);

    function refresh(){
      if (sem.checked){
        input.value = '';
        input.setAttribute('readonly', 'readonly');
        input.removeAttribute('pattern');
        input.placeholder = 'Gerado automaticamente';
        ant.disabled = true; ant.checked = false;
      } else {
        input.removeAttribute('readonly');
        input.placeholder = '000.000000000-0';
        ant.disabled = false;
      }
      if (ant.checked){
        input.removeAttribute('pattern');
        input.placeholder = 'Valor livre (formato antigo)';
      } else if (!sem.checked){
        input.setAttribute('pattern', '^\\d{3}\\.\\d{9}-\\d$');
        input.value = fmt(onlyDigits(input.value));
        input.placeholder = '000.000000000-0';
      }
      toPayload();
    }

    ant.addEventListener('change', refresh);
    sem.addEventListener('change', refresh);
    input.addEventListener('input', function(){
      if (!ant.checked && !sem.checked){
        input.value = fmt(onlyDigits(input.value));
      }
      toPayload();
    });
    refresh();
  }

  function addRow(){
    var cont = id('multi-rows');
    var idx = (cont.querySelectorAll('.multi-row').length || 0) + 1;
    cont.insertAdjacentHTML('beforeend', rowTemplate(idx));
    var row = cont.lastElementChild;
    applyMask(row);
    qs('.rm', row).addEventListener('click', function(){
      row.remove(); toPayload();
    });
    toPayload();
    return row;
  }

  function hydrateFromPayload(initialPayload){
    var cont = id('multi-rows');
    if (!cont) return;
    cont.innerHTML = '';
    var arr = [];
    try { arr = JSON.parse(initialPayload || "[]") || []; } catch(e){ arr = []; }
    if (!arr.length) return;

    arr.forEach(function(item){
      var row = addRow();
      var np = qs('.fld-npat', row);
      var ant = qs('.fld-ant', row);
      var sem = qs('.fld-sem', row);
      var loc = qs('.fld-loc', row);

      if (typeof item.numero_patrimonial !== 'undefined' && np){
        np.value = item.numero_patrimonial || '';
      }
      if (typeof item.numero_formato_antigo !== 'undefined' && ant){
        ant.checked = !!item.numero_formato_antigo;
      }
      if (typeof item.sem_numeracao !== 'undefined' && sem){
        sem.checked = !!item.sem_numeracao;
      }
      if (typeof item.localizacao !== 'undefined' && loc){
        loc.value = item.localizacao || '';
      }
      ant && ant.dispatchEvent(new Event('change'));
      sem && sem.dispatchEvent(new Event('change'));
      np && np.dispatchEvent(new Event('input'));
    });
    toPayload();
  }

  function showError(containerId, msgs){
    var box = id(containerId);
    if (!box) return;
    if (!msgs || !msgs.length){
      box.classList.add('hide'); box.innerHTML = ''; return;
    }
    box.classList.remove('hide');
    box.innerHTML = msgs.map(function(m){ return '<div>'+m+'</div>'; }).join('');
    box.scrollIntoView({behavior:'smooth', block:'center'});
  }

  function validateMultiRows(){
    toPayload();
    var rows = qsa('#multi-rows .multi-row');
    var errors = [];
    if (!rows.length){
      errors.push('Adicione ao menos uma linha no modo Múltiplos Bens.');
    }
    rows.forEach(function(r, i){
      var idx = i + 1;
      var np = qs('.fld-npat', r);
      var sem = qs('.fld-sem', r);
      var npVal = (np.value || '').trim();
      var semVal = !!sem.checked;
      if (!semVal && !npVal){
        errors.push('Linha '+idx+': Informe o Nº Patrimonial ou marque "Sem numeração".');
        np.classList.add('error'); np.style.borderColor = '#ba2121';
      } else {
        np.classList.remove('error'); np.style.borderColor = '';
      }
    });
    showError('multi-errors', errors);
    return errors.length === 0;
  }

  function labelFor(field){
    var wrap = field.closest('.form-row') || field.parentNode;
    if (!wrap) return field.name || field.id || 'Campo obrigatório';
    var lbl = wrap.querySelector('label');
    if (lbl && lbl.textContent) return lbl.textContent.replace(':','').trim();
    return field.name || field.id || 'Campo obrigatório';
  }

  function cleanBaseHighlights(form){
    qsa('.form-row .error', form).forEach(function(el){ el.classList.remove('error'); });
    qsa('.form-row input, .form-row select, .form-row textarea', form).forEach(function(el){ el.style.borderColor = ''; });
  }

  function markErrorField(field){
    var wrap = field.closest('.form-row') || field.parentNode;
    if (wrap) wrap.classList.add('error');
    field.style.borderColor = '#ba2121';
  }

  function isEmptyField(field){
    if (field.disabled) return false;
    var type = (field.type || '').toLowerCase();
    if (type === 'checkbox' || type === 'radio'){
      var group = qsa('[name="'+field.name+'"]', field.ownerDocument);
      if (group && group.length > 1){
        for (var i=0;i<group.length;i++) if (group[i].checked) return false;
        return true;
      }
      return !field.checked;
    }
    return (field.value == null || String(field.value).trim() === '');
  }

  function applyRequiredFromDjango(form){
    qsa('.form-row.required', form).forEach(function(row){
      qsa('input, select, textarea', row).forEach(function(el){
        if (el.closest('#multi-container')) return;
        el.setAttribute('required', 'required');
      });
    });
    qsa('.admin-autocomplete', form).forEach(function(wrap){
      var visible = qs('input.select2-search__field, input[type="search"], input[type="text"]', wrap);
      var hidden = qs('select, input[type="hidden"]', wrap);
      if (hidden && (hidden.required || hidden.closest('.form-row')?.classList.contains('required'))){
        if (visible) visible.setAttribute('required', 'required');
      }
    });
  }

  function collectRequiredFields(form){
    var req = qsa('input[required], select[required], textarea[required]', form);
    qsa('.form-row.required input, .form-row.required select, .form-row.required textarea', form).forEach(function(el){
      if (req.indexOf(el) === -1) req.push(el);
    });
    req = req.filter(function(el){ return !el.closest('#multi-container'); });
    return req;
  }

  function validateBaseRequired(form){
    cleanBaseHighlights(form);
    applyRequiredFromDjango(form);
    var errors = [];
    var req = collectRequiredFields(form);
    req.forEach(function(field){
      if (isEmptyField(field)){
        errors.push('Preencha o campo obrigatório: <strong>'+labelFor(field)+'</strong>.');
        markErrorField(field);
      }
    });
    showError('base-required-errors', errors);
    return errors.length === 0;
  }

  function initMulti(){
    var root = id('multi-inline-root');
    if (!root) return;

    var form = qs('form');
    if (!form) return;

    // Injeta bloco completo logo após o campo foto (ou no fim do form)
    var anchor = qs('.form-row.field-foto');
    var wrapper = document.createElement('div');
    wrapper.innerHTML = multiHTML();
    if (anchor && anchor.parentNode){ anchor.parentNode.insertBefore(wrapper, anchor.nextSibling); }
    else { form.appendChild(wrapper); }

    var multi = id('multi-container');
    var errorBase = id('base-required-errors');
    var addBtn = id('multi-add');

    // Bind dinâmicos
    if (addBtn && !addBtn.dataset.bound){
      addBtn.dataset.bound = "1";
      addBtn.addEventListener('click', addRow);
    }
    form.addEventListener('input', toPayload);
    form.addEventListener('change', toPayload);

    // Hidden para garantir envio de modo
    var hiddenModo = document.createElement('input');
    hiddenModo.type = 'hidden';
    hiddenModo.name = 'cadastro_modo';
    form.appendChild(hiddenModo);

    function setMode(force){
      var checked = qs('input[name="cadastro_modo"]:checked');
      var val = (checked && checked.value) || 'unico';
      if (force === 'multi'){
        var radioMulti = qs('input[name="cadastro_modo"][value="multi"]');
        if (radioMulti){ radioMulti.checked = true; val = 'multi'; }
      }
      var singleWraps = ['numero_patrimonial', 'numero_formato_antigo', 'sem_numeracao', 'localizacao'].map(function(f){
        var row = qs('.form-row.field-' + f) || (id('id_'+f) && id('id_'+f).closest('.form-row'));
        return row || null;
      }).filter(Boolean);

      if (val === 'multi'){
        multi.classList.remove('hide');
        singleWraps.forEach(function(w){ w.style.display = 'none'; });
      } else {
        multi.classList.add('hide');
        singleWraps.forEach(function(w){ w.style.display = ''; });
      }
      toPayload();
    }

    // Radios
    qsa('input[name="cadastro_modo"]').forEach(function(r){ r.addEventListener('change', function(){ setMode(); }); });

    var initialPayload = (function(){
        var tag = id('multi-inline-data');
        return (tag && tag.textContent) ? tag.textContent : "[]";
    })();

    hydrateFromPayload(initialPayload);
    var forceMultiFlag = root.getAttribute('data-force-multi') === '1';
    setMode(forceMultiFlag ? 'multi' : null);

    function guardSubmit(ev){
      toPayload();
      var okBase = validateBaseRequired(form);
      if (!okBase){ ev.preventDefault(); ev.stopPropagation(); return; }

      var isMulti = !multi.classList.contains('hide');
      var hasRows = qsa('#multi-rows .multi-row').length > 0;
      var radioMultiChecked = !!qs('input[name="cadastro_modo"][value="multi"]:checked');
      if (isMulti){
        var okMulti = validateMultiRows();
        if (!okMulti){ ev.preventDefault(); ev.stopPropagation(); return; }
      }
      if (hasRows || radioMultiChecked){
        hiddenModo.value = 'multi';
        var radioMulti = qs('input[name="cadastro_modo"][value="multi"]');
        if (radioMulti) radioMulti.checked = true;
      } else {
        var checked = qs('input[name="cadastro_modo"]:checked');
        hiddenModo.value = checked ? checked.value : 'unico';
      }
    }

    form.addEventListener('submit', guardSubmit);
    ['_save','_addanother','_continue'].forEach(function(name){
      var btn = qs('input[name="'+name+'"]');
      if (btn && !btn.dataset.bound){
        btn.dataset.bound = "1";
        btn.addEventListener('click', guardSubmit);
      }
    });

    document.addEventListener('input', function(){ showError('base-required-errors', []); showError('multi-errors', []); });
  }

  document.addEventListener('DOMContentLoaded', function(){
    bindCurrencyMask();
    bindSingleNumeroPatrimonialMask();
    initMulti();
  });
})();