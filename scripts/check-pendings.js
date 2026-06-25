window.__abaPendentesJaAtiva = function () {
  return Array.from(document.querySelectorAll('a, button, li')).some(el => {
    var t = (el.innerText || '').trim();
    if (!/pendentes?/i.test(t)) return false;
    return (
      el.classList.contains('active') ||
      el.getAttribute('aria-selected') === 'true' ||
      (el.parentElement && el.parentElement.classList.contains('active'))
    );
  });
};
