// Componentes de Alpine y ajustes de HTMX del sitio.
//
// La Content-Security-Policy no permite scripts en línea ni eval. Por eso se usa la
// versión CSP de Alpine (@alpinejs/csp), que solo acepta expresiones simples en el HTML,
// y la lógica que necesita JavaScript completo vive aquí como Alpine.data(). Este archivo
// se carga con defer antes de Alpine, para registrar los componentes en `alpine:init`.

document.addEventListener("alpine:init", function () {
  // Botón de tema claro u oscuro. Recuerda la elección con $persist; sin elección, sigue
  // la preferencia del sistema.
  Alpine.data("selectorTema", function () {
    return {
      tema: this.$persist(null).as("agroia-tema"),
      get oscuro() {
        if (this.tema) return this.tema === "agroia-oscuro";
        return window.matchMedia("(prefers-color-scheme: dark)").matches;
      },
      get etiqueta() {
        return this.oscuro ? "Usar tema claro" : "Usar tema oscuro";
      },
      get pulsado() {
        return this.oscuro ? "true" : "false";
      },
      alternar() {
        this.tema = this.oscuro ? "agroia" : "agroia-oscuro";
        document.documentElement.dataset.theme = this.tema;
      },
    };
  });

  // <details> de los filtros del catálogo: abierto sin JavaScript; en celular se pliega
  // si no hay filtros activos (data-hay-filtros).
  Alpine.data("plegarEnCelular", function () {
    return {
      init() {
        var celular = window.matchMedia("(max-width: 767px)").matches;
        if (celular && this.$el.dataset.hayFiltros !== "true") this.$el.open = false;
      },
    };
  });
});

// Filtros del catálogo con HTMX: no enviar los campos vacíos, para que la URL quede limpia
// y se pueda compartir (antes era un hx-on en línea).
document.addEventListener("htmx:configRequest", function (evento) {
  if (!evento.detail.elt || !evento.detail.elt.hasAttribute("data-quitar-vacios")) return;
  var parametros = evento.detail.parameters;
  if (parametros instanceof FormData) {
    Array.from(parametros.keys()).forEach(function (clave) {
      if (parametros.get(clave) === "") parametros.delete(clave);
    });
  } else {
    Object.keys(parametros).forEach(function (clave) {
      if (parametros[clave] === "") delete parametros[clave];
    });
  }
});
