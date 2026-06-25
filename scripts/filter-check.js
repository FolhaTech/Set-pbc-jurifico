window.__filtroResponsavelPreservado = function () {
  var el = document.getElementById(
    'publication-multiselect-filter-with-search-select-responsible-user-filter'
  );
  if (!el) return true;
  var v = (el.value || el.innerText || '').trim();
  return v.length > 0;
};
