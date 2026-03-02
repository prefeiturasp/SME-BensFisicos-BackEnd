
(function(){
  function id(s){ return document.getElementById(s); }
  function qs(s, r){ return (r || document).querySelector(s); }
  function qsa(s, r){ return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
  function onlyDigits(s){ return (s||'').replace(/\D/g,''); }
  function fmt(d){
    d = (d||'').slice(0,13);
    const p1=d.slice(0,3), p2=d.slice(3,12), p3=d.slice(12,13);
    if (d.length <= 3) return p1;
    if (d.length <= 12) return p1 + '.' + p2;
    return p1 + '.' + p2 + '-' + p3;
  }

  function formatBRMoneyFromDigits(digits){
    if (!digits) digits = "0";
    digits = digits.replace(/^0+/, "") || "0";
    if (digits.length === 1) digits = "0" + digits;
    if (digits.length === 2) digits = "0" + digits;
    const cents = digits.slice(-2);
    const ints  = digits.slice(0, -2);
    const withThousand = ints.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return withThousand + "," + cents;
  }

  function bindCurrencyMask(){
    const el = id("id_valor_unitario");
    if (!el || el.dataset.boundMask === "1") return;
    el.dataset.boundMask = "1";
    (function init(){
      const raw = (el.value?.trim() || "");
      if (raw && !/^\d{1,3}(\.\d{3})*,\d{2}$/.test(raw)){
        const digits = raw.replace(/[^\d]/g, "");
        el.value = formatBRMoneyFromDigits(digits);
      }
    })();
    el.addEventListener("input", function(){
      const digits = (el.value || "").replace(/[^\d]/g, "");
      el.value = formatBRMoneyFromDigits(digits);
    });
    el.addEventListener("blur", function(){
      const digits = (el.value || "").replace(/[^\d]/g, "");
      el.value = formatBRMoneyFromDigits(digits);
    });
    el.setAttribute("required", "required");
  }

  function bindSingleNumeroPatrimonialMask(){
    const np   = id('id_numero_patrimonial');
    const ant  = id('id_numero_formato_antigo');
    const sem  = id('id_sem_numeracao');
    const isEdit = qsa('input[name="cadastro_modo"]').length === 0;
    if (!np || !ant) return;

    function setReadOnly(on){
      if (on){ np.setAttribute('readonly','readonly'); np.setAttribute('aria-readonly','true'); }
      else { np.removeAttribute('readonly'); np.removeAttribute('aria-readonly'); }
    }

    let didInitialShow = false;

    function mutuallyExclusive(changed){
      
      if (!ant || !sem) return;
      if (changed === 'sem' && sem.checked && ant.checked){ ant.checked = false; }
      if (changed === 'ant' && ant.checked && sem.checked){ sem.checked = false; }
    }

    function applyPatternAndMask(){
      
      if (!ant?.checked){
        np.setAttribute('pattern', '^\\d{3}\\.\\d{9}-\\d$');
        np.placeholder = '000.000000000-0';
        np.value = fmt(onlyDigits(np.value));
      } else {
        np.removeAttribute('pattern');
        np.placeholder = 'Valor livre (formato antigo)';
      }
    }

    function handleSemMarcadoEdit() {
      setReadOnly(false);
      np.removeAttribute('pattern');
      np.placeholder = 'Sem numeração';
      if (!didInitialShow) {
        didInitialShow = true;
        return true;
      }
      return false;
    }

    function handleSemMarcadoCreate() {
      setReadOnly(true);
      np.removeAttribute('pattern');
      np.placeholder = 'Gerado automaticamente';
      np.value = '';
      if (ant) { ant.disabled = true; ant.checked = false; }
    }

    function refresh(){
      const semMarcado = !!sem?.checked;

      if (semMarcado) {
        if (isEdit) {
          handleSemMarcadoEdit();
          return;
        }
        handleSemMarcadoCreate();
        return;
      }
      setReadOnly(false);
      if (ant) ant.disabled = false;

      if (ant?.checked) {
        np.removeAttribute('pattern');
        np.placeholder = 'Valor livre (formato antigo)';
        return;
      }
      applyPatternAndMask();
    }

    
    if (ant) ant.addEventListener('change', function(){
      mutuallyExclusive('ant');
      refresh();
    });

    if (sem) sem.addEventListener('change', function(){
      mutuallyExclusive('sem');
      refresh();
    });

    np.addEventListener('input', function(){
      
      if (isEdit && sem?.checked){
        sem.checked = false;          
        mutuallyExclusive('sem');
      }
      
      const semMarcado = !!sem?.checked;
      if (!ant?.checked && !semMarcado){
        np.value = fmt(onlyDigits(np.value));
        np.setAttribute('pattern', '^\\d{3}\\.\\d{9}-\\d$');
        np.placeholder = '000.000000000-0';
      } else if (ant?.checked){
        np.removeAttribute('pattern');
        np.placeholder = 'Valor livre (formato antigo)';
      } else if (semMarcado){
        np.removeAttribute('pattern');
        np.placeholder = 'Sem numeração';
      }
    });

    
    refresh();
  }

  
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
    const rows = qsa('#multi-rows .multi-row');
    const out = [];
    rows.forEach(function(r){
      out.push({
        numero_patrimonial: (qs('.fld-npat', r)?.value || '').trim(),
        numero_formato_antigo: !!qs('.fld-ant', r)?.checked,
        sem_numeracao: !!qs('.fld-sem', r)?.checked,
        localizacao: (qs('.fld-loc', r)?.value || '').trim()
      });
    });
    const hidden = id('id_multi_payload');
    if (hidden) hidden.value = JSON.stringify(out);
  }

  function applyMask(row){
    const input = qs('.fld-npat', row);
    const ant = qs('.fld-ant', row);
    const sem = qs('.fld-sem', row);

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
      if (!ant?.checked && !sem?.checked){
        input.value = fmt(onlyDigits(input.value));
      }
      toPayload();
    });
    refresh();
  }

  function addRow(){
    const cont = id('multi-rows');
    const idx = (cont.querySelectorAll('.multi-row').length || 0) + 1;
    cont.insertAdjacentHTML('beforeend', rowTemplate(idx));
    const row = cont.lastElementChild;
    applyMask(row);
    qs('.rm', row).addEventListener('click', function(){
      row.remove(); toPayload();
    });
    toPayload();
    return row;
  }

  function hydrateFromPayload(initialPayload){
    const cont = id('multi-rows');
    if (!cont) return;
    cont.innerHTML = '';
    let arr = [];
    try { arr = JSON.parse(initialPayload || "[]") || []; } catch (e) {
      console.warn("bem_patrimonial: payload inválido, usando lista vazia", e);
      arr = [];
    }
    if (!arr.length) return;

    arr.forEach(function(item){
      const row = addRow();
      const np = qs('.fld-npat', row);
      const ant = qs('.fld-ant', row);
      const sem = qs('.fld-sem', row);
      const loc = qs('.fld-loc', row);

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
      ant?.dispatchEvent(new Event('change'));
      sem?.dispatchEvent(new Event('change'));
      np?.dispatchEvent(new Event('input'));
    });
    toPayload();
  }

  function showError(containerId, msgs){
    const box = id(containerId);
    if (!msgs || !msgs.length){
      if (box){
        box.classList.add('hide');
        box.innerHTML = '';
      }
      return;
    }
    if (!box) return;
    box.classList.remove('hide');
    box.innerHTML = msgs.map(function(m){ return '<div>'+m+'</div>'; }).join('');
    box.scrollIntoView({behavior:'smooth', block:'center'});
  }

  function validateMultiRows(){
    toPayload();
    const rows = qsa('#multi-rows .multi-row');
    const errors = [];

    if (!rows.length){
        errors.push('Adicione ao menos uma linha no modo Múltiplos Bens.');
    }

    function markErr(input){
        input.classList.add('error');
        input.style.setProperty('border-color', '#ba2121', 'important');
        input.style.setProperty('outline', '2px solid rgba(186,33,33,.15)', 'important');
        input.style.setProperty('outline-offset', '1px', 'important');
    }
    function clearErr(input){
        input.classList.remove('error');
        input.style.removeProperty('border-color');
        input.style.removeProperty('outline');
        input.style.removeProperty('outline-offset');
    }

    rows.forEach(function(r, i){
        const idx = i + 1;
        const np  = qs('.fld-npat', r);
        const sem = qs('.fld-sem', r);
        const loc = qs('.fld-loc', r);

        const npVal  = (np?.value || '').trim();
        const semVal = !!sem?.checked;
        const locVal = (loc?.value || '').trim();

        r.classList.remove('invalid');

        if (!semVal && !npVal){
        errors.push('Linha '+idx+': Informe o Nº Patrimonial ou marque "Sem numeração".');
        markErr(np);
        r.classList.add('invalid');
        } else {
        clearErr(np);
        }

        if (!locVal){
        errors.push('Linha '+idx+': Informe a Localização (obrigatória).');
        markErr(loc);
        r.classList.add('invalid');
        } else {
        clearErr(loc);
        }
    });

    showError('multi-errors', errors);
    return errors.length === 0;
    }

  function labelFor(field){
    const wrap = field.closest('.form-row') || field.parentNode;
    if (!wrap) return field.name || field.id || 'Campo obrigatório';
    const lbl = wrap.querySelector('label');
    if (lbl?.textContent) return lbl.textContent.replace(':','').trim();
    return field.name || field.id || 'Campo obrigatório';
  }

  function cleanBaseHighlights(form){
    qsa('.form-row .error', form).forEach(function(el){ el.classList.remove('error'); });
    qsa('.form-row input, .form-row select, .form-row textarea', form).forEach(function(el){ el.style.borderColor = ''; });
  }

  function markErrorField(field){
    const wrap = field.closest('.form-row') || field.parentNode;
    if (wrap) wrap.classList.add('error');
    field.style.borderColor = '#ba2121';
  }

  function isEmptyField(field){
    if (field.disabled) return false;
    const type = (field.type || '').toLowerCase();
    if (type === 'checkbox' || type === 'radio'){
      const group = qsa('[name="'+field.name+'"]', field.ownerDocument);
      if (group && group.length > 1){
        for (const item of group) { if (item.checked) return false; }
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
      const visible = qs('input.select2-search__field, input[type="search"], input[type="text"]', wrap);
      const hidden = qs('select, input[type="hidden"]', wrap);
      if (hidden && (hidden.required || hidden.closest('.form-row')?.classList.contains('required'))){
        if (visible) visible.setAttribute('required', 'required');
      }
    });
  }

  function collectRequiredFields(form){
    let req = qsa('input[required], select[required], textarea[required]', form);
    qsa('.form-row.required input, .form-row.required select, .form-row.required textarea', form).forEach(function(el){
      if (req.indexOf(el) === -1) req.push(el);
    });
    req = req.filter(function(el){ return !el.closest('#multi-container'); });
    return req;
  }

  function validateBaseRequired(form){
    cleanBaseHighlights(form);
    applyRequiredFromDjango(form);
    const errors = [];
    const req = collectRequiredFields(form);
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
    const root = id('multi-inline-root');
    if (!root) return;

    const form = qs('form');
    if (!form) return;

    const anchor = qs('.form-row.field-numero_processo');
    const wrapper = document.createElement('div');
    wrapper.innerHTML = multiHTML();
    if (anchor?.parentNode){ anchor.parentNode.insertBefore(wrapper, anchor.nextSibling); }
    else { form.appendChild(wrapper); }

    const locSingle = id('id_localizacao');
    if (locSingle) locSingle.setAttribute('required', 'required');

    const multi = id('multi-container');
    const addBtn = id('multi-add');

    if (addBtn && !addBtn.dataset.bound){
        addBtn.dataset.bound = "1";
        addBtn.addEventListener('click', addRow);
    }
    form.addEventListener('input', toPayload);
    form.addEventListener('change', toPayload);

    const hiddenModo = document.createElement('input');
    hiddenModo.type = 'hidden';
    hiddenModo.name = 'cadastro_modo';
    form.appendChild(hiddenModo);

    function setMode(force){
        const checked = qs('input[name="cadastro_modo"]:checked');
        let val = (checked?.value) || 'unico';
        if (force === 'multi'){
        const radioMulti = qs('input[name="cadastro_modo"][value="multi"]');
        if (radioMulti){ radioMulti.checked = true; val = 'multi'; }
        }
        const singleWraps = ['numero_patrimonial', 'numero_formato_antigo', 'sem_numeracao', 'localizacao'].map(function(f){
        const row = qs('.form-row.field-' + f) || id('id_'+f)?.closest('.form-row');
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

    qsa('input[name="cadastro_modo"]').forEach(function(r){ r.addEventListener('change', function(){ setMode(); }); });

    const initialPayload = (function(){
        const tag = id('multi-inline-data');
        return (tag?.textContent) ? tag.textContent : "[]";
    })();

    hydrateFromPayload(initialPayload);
    const forceMultiFlag = root.getAttribute('data-force-multi') === '1';
    setMode(forceMultiFlag ? 'multi' : null);

    function guardSubmit(ev){
        toPayload();
        const okBase = validateBaseRequired(form);
        if (!okBase){ ev.preventDefault(); ev.stopPropagation(); return; }

        const isMulti = !multi.classList.contains('hide');
        const hasRows = qsa('#multi-rows .multi-row').length > 0;
        const radioMultiChecked = !!qs('input[name="cadastro_modo"][value="multi"]:checked');
        if (isMulti){
        const okMulti = validateMultiRows();
        if (!okMulti){ ev.preventDefault(); ev.stopPropagation(); return; }
        }
        if (hasRows || radioMultiChecked){
        hiddenModo.value = 'multi';
        const radioMulti = qs('input[name="cadastro_modo"][value="multi"]');
        if (radioMulti) radioMulti.checked = true;
        } else {
        const checked = qs('input[name="cadastro_modo"]:checked');
        hiddenModo.value = checked?.value ?? 'unico';
        }
    }

    form.addEventListener('submit', guardSubmit);
    ['_save','_addanother','_continue'].forEach(function(name){
        const btn = qs('input[name="'+name+'"]');
        if (btn && !btn.dataset.bound){
        btn.dataset.bound = "1";
        btn.addEventListener('click', guardSubmit);
        }
    });

    document.addEventListener('input', function(){
        showError('base-required-errors', []);
        showError('multi-errors', []);
    });
   }

  document.addEventListener('DOMContentLoaded', function(){
    bindCurrencyMask();
    bindSingleNumeroPatrimonialMask();
    initMulti();
  });
})();