/**
 * Previne duplo clique nos botões de submit do Django Admin
 * Desabilita botões após o primeiro clique e mostra feedback visual
 */
(function() {
    'use strict';
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPreventDoubleSubmit);
    } else {
        initPreventDoubleSubmit();
    }
    
    function initPreventDoubleSubmit() {
        const form = document.querySelector('form#movimentacaobempatrimonial_form');
        
        if (!form) {
            const forms = document.querySelectorAll('form');
            if (forms.length === 0) return;
            
            forms.forEach(function(f) {
                if (f.querySelector('[name="_save"], [name="_addanother"], [name="_continue"]')) {
                    applyProtection(f);
                }
            });
        } else {
            applyProtection(form);
        }
    }
    
    function applyProtection(form) {
        let isSubmitting = false;
        
        form.addEventListener('submit', function(e) {
            if (isSubmitting) {
                e.preventDefault();
                return false;
            }
            
            isSubmitting = true;
            
            const submitButtons = form.querySelectorAll(
                'input[type="submit"], button[type="submit"], ' +
                '[name="_save"], [name="_addanother"], [name="_continue"]'
            );
            
            submitButtons.forEach(function(button) {
                button.disabled = true;
                
                if (button.value) {
                    button.dataset.originalValue = button.value;
                    button.value = 'Salvando...';
                } else if (button.textContent) {
                    button.dataset.originalText = button.textContent;
                    button.textContent = 'Salvando...';
                }
                
                button.classList.add('disabled', 'submitting');
            });
            
            setTimeout(function() {
                if (isSubmitting) {
                    isSubmitting = false;
                    submitButtons.forEach(function(button) {
                        button.disabled = false;
                        
                        if (button.dataset.originalValue) {
                            button.value = button.dataset.originalValue;
                        } else if (button.dataset.originalText) {
                            button.textContent = button.dataset.originalText;
                        }
                        
                        button.classList.remove('disabled', 'submitting');
                    });
                }
            }, 15000);
        });
    }
})();
