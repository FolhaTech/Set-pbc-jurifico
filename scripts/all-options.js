window.__selectOption = function select(texto_alvo) {
  var alvo = `${texto_alvo}`.toLocaleLowerCase();
  var todos = document.querySelectorAll("a, li, button, span, div");
  for (var i = 0; i < todos.length; i++) {
    var txt = (todos[i].innerHTML || "").toLocaleLowerCase().trim();
    if (
      (txt === alvo || txt.includes(alvo)) &&
      todos[i].offsetParent !== null
    ) {
      {
        todos[i].click();
        return txt;
      }
    }
  }
  return null;
};
