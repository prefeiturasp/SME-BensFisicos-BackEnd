(function() {
    function isAutocompleteUrl(url) {
        return typeof url === 'string' && url.includes('/admin/autocomplete/');
    }

    globalThis.AdminAutocompleteFilter = { isAutocompleteUrl: isAutocompleteUrl };
})();
