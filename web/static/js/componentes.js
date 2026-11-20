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

  // Chat con AgroIA: muestra al instante la pregunta enviada y desactiva el botón mientras
  // responde el agente. Solo reacciona a las peticiones del formulario de la pregunta.
  Alpine.data("chat", function () {
    return {
      enviando: false,
      pregunta: "",
      enviar(evento) {
        var campo = evento.target.querySelector("textarea");
        if (!campo || !campo.value.trim()) return;
        this.pregunta = campo.value.trim();
        this.enviando = true;
      },
      terminar(evento) {
        var campo = evento.target.querySelector("textarea");
        if (!campo) return;
        this.enviando = false;
        if (evento.detail.successful) campo.value = "";
        var mensajes = document.getElementById("mensajes");
        if (mensajes && mensajes.lastElementChild) {
          mensajes.lastElementChild.scrollIntoView({ block: "nearest" });
        }
      },
    };
  });

  // Foto del diagnóstico: vista previa antes de enviarla y validación de tipo y tamaño en el
  // navegador (el gateway lo vuelve a validar). La vista previa usa una URL blob: (CSP).
  Alpine.data("vistaPrevia", function () {
    return {
      url: "",
      error: "",
      elegir(evento) {
        var archivo = evento.target.files && evento.target.files[0];
        if (this.url) URL.revokeObjectURL(this.url);
        this.url = "";
        this.error = "";
        if (!archivo) return;
        if (["image/jpeg", "image/png"].indexOf(archivo.type) === -1) {
          this.error = "Elige una foto JPG o PNG.";
        } else if (archivo.size > 5 * 1024 * 1024) {
          this.error = "La foto pesa más de 5 MB.";
        }
        if (this.error) {
          evento.target.value = "";
          return;
        }
        this.url = URL.createObjectURL(archivo);
      },
      get lista() {
        return this.url !== "";
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
