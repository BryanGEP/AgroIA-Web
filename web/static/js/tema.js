// Aplica el tema elegido antes de pintar, para que no parpadee. Se carga en el <head> sin
// defer; está en un archivo (y no en línea) para cumplir la Content-Security-Policy.
try {
  var tema = JSON.parse(localStorage.getItem("agroia-tema"));
  if (tema) document.documentElement.dataset.theme = tema;
} catch (e) {}
