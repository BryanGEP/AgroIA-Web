// Componentes de Alpine y ajustes de HTMX del sitio.
//
// La Content-Security-Policy no permite scripts en línea ni eval. Por eso se usa la
// versión CSP de Alpine (@alpinejs/csp), que solo acepta expresiones simples en el HTML,
// y la lógica que necesita JavaScript completo vive aquí como Alpine.data(). Este archivo
// se carga con defer antes de Alpine, para registrar los componentes en `alpine:init`.

// Fuera de los datos de Alpine: los objetos del navegador (audio, reconocimiento de voz) no
// deben envolverse en sus proxies reactivos.
var audioDelWidget = null;
var reconocedor = null;
var ReconocimientoDeVoz = window.SpeechRecognition || window.webkitSpeechRecognition || null;
var MICROFONO_ACEPTADO = "agroia-microfono-aceptado";
var ERRORES_DE_VOZ = {
  "not-allowed": "No diste permiso para usar el micrófono. Puedes activarlo en la configuración del navegador.",
  "service-not-allowed": "Tu navegador no permite el dictado por voz en este sitio.",
  "no-speech": "No escuchamos nada. Intenta de nuevo.",
  "audio-capture": "No encontramos un micrófono.",
  network: "No hay conexión con el servicio de dictado por voz.",
  inicio: "No pudimos empezar a escuchar. Intenta de nuevo.",
};

// localStorage puede fallar (modo privado, bloqueado): nunca rompe el widget.
function guardado(clave) {
  try {
    return window.localStorage.getItem(clave) === "true";
  } catch (e) {
    return false;
  }
}
function guardar(clave, valor) {
  try {
    window.localStorage.setItem(clave, valor);
  } catch (e) {
    /* sin almacenamiento: se volverá a pedir el aviso */
  }
}

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

  // Chat con AgroIA, en /agroia/ y en el widget: muestra al instante la pregunta enviada y
  // desactiva el botón mientras responde el agente. Busca su lista de mensajes
  // ([data-mensajes]) dentro de su propio componente, no por id.
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
      // Enter envía; Mayús+Enter hace un salto de línea.
      enviarConEnter(evento) {
        if (evento.shiftKey || evento.isComposing) return;
        evento.preventDefault();
        var formulario = evento.target.form;
        if (formulario && evento.target.value.trim()) formulario.requestSubmit();
      },
      terminar(evento) {
        this.enviando = false;
        var campo = evento.target.querySelector("textarea");
        // Si la pregunta no entró (por ejemplo, muchas preguntas seguidas), el servidor lo
        // avisa con X-Conservar-Pregunta y el texto se queda para enviarlo después.
        var xhr = evento.detail.xhr;
        var conservar = xhr && xhr.getResponseHeader("X-Conservar-Pregunta");
        if (campo && evento.detail.successful && !conservar) campo.value = "";
        // Al tocar una sugerencia, la respuesta quita su formulario: ya no tiene componente.
        var raiz = this.$root;
        var mensajes = raiz && raiz.querySelector("[data-mensajes]");
        if (mensajes && mensajes.lastElementChild) {
          mensajes.lastElementChild.scrollIntoView({ block: "nearest" });
        }
      },
    };
  });

  // «Copiar» en cada respuesta de AgroIA: el texto plano (sin HTML ni fuentes) con la
  // Clipboard API. Si el navegador no la permite (sin contexto seguro), no aparece.
  Alpine.data("copiar", function () {
    return {
      copiado: false,
      anuncio: "",
      get disponible() {
        return Boolean(window.isSecureContext && navigator.clipboard && navigator.clipboard.writeText);
      },
      get etiqueta() {
        return this.copiado ? "Copiado" : "Copiar";
      },
      copiar() {
        var self = this;
        var texto = this.$refs.respuesta.innerText.trim();
        navigator.clipboard.writeText(texto).then(
          function () {
            self.copiado = true;
            self.anuncio = "Copiamos la respuesta.";
            window.setTimeout(function () {
              self.copiado = false;
              self.anuncio = "";
            }, 2000);
          },
          function () {
            self.anuncio = "No se pudo copiar la respuesta.";
          }
        );
      },
    };
  });

  // Widget flotante de AgroIA (agroia/parciales/_widget.html).
  // - Abierto o cerrado se recuerda por pestaña (sessionStorage); el sonido, en el navegador.
  // - Carga diferida: el contenido se pide (evento `cargar` de HTMX) la primera vez que se
  //   abre, o al cargar la página si estaba abierto o hay una pregunta pendiente.
  // - Foco: en celular el panel es modal (pantalla completa, foco atrapado); en escritorio
  //   flota sin atraparlo. Al abrir entra al campo; al cerrar vuelve a la burbuja.
  // - En celular la burbuja se oculta mientras se baja por la página (para no tapar el
  //   texto) y vuelve al subir o al detenerse. No se oculta con el panel abierto ni con una
  //   respuesta nueva sin leer, y al recibir el foco vuelve a aparecer. La animación está
  //   en fuente.css (.burbuja-agroia) y se quita con prefers-reduced-motion.
  Alpine.data("widgetAgroia", function () {
    return {
      abierto: this.$persist(false).as("agroia-widget-abierto").using(sessionStorage),
      sonido: this.$persist(false).as("agroia-widget-sonido"),
      nueva: false,
      cargado: false,
      celular: false,
      enfocarAlCargar: false,
      anuncio: "",
      bajando: false,
      init() {
        var self = this;
        var consulta = window.matchMedia("(max-width: 639px)");
        this.celular = consulta.matches;
        consulta.addEventListener("change", function (evento) {
          self.celular = evento.matches;
        });
        if (this.abierto || this.$el.dataset.pendiente === "true") this.cargar();
        this.vigilarDesplazamiento();
        // Política de reproducción automática: el audio solo arranca con un gesto.
        ["pointerdown", "keydown"].forEach(function (tipo) {
          document.addEventListener(tipo, function () { self.prepararAudio(); }, { once: true });
        });
      },
      get cerrado() {
        return !this.abierto;
      },
      get expandido() {
        return this.abierto ? "true" : "false";
      },
      get modal() {
        return this.celular ? "true" : "false";
      },
      vigilarDesplazamiento() {
        var self = this;
        var anterior = window.scrollY;
        var espera = null;
        window.addEventListener("scroll", function () {
          var actual = window.scrollY;
          var delta = actual - anterior;
          anterior = actual;
          if (!self.celular) { self.bajando = false; return; }
          if (delta > 4 && actual > 80) self.bajando = true;
          else if (delta < -4) self.bajando = false;
          window.clearTimeout(espera);
          espera = window.setTimeout(function () { self.bajando = false; }, 700);
        }, { passive: true });
      },
      mostrarBurbuja() {
        this.bajando = false;
      },
      get burbujaEscondida() {
        return this.bajando && !this.abierto && !this.nueva ? "true" : "false";
      },
      get burbujaVisible() {
        return !(this.abierto && this.celular);
      },
      get etiquetaBurbuja() {
        if (this.abierto) return "Cerrar el chat de AgroIA";
        return this.nueva ? "Abrir el chat de AgroIA: hay una respuesta nueva" : "Abrir el chat de AgroIA";
      },
      get silencio() {
        return !this.sonido;
      },
      get sonidoPulsado() {
        return this.sonido ? "true" : "false";
      },
      get etiquetaSonido() {
        return this.sonido ? "Silenciar el aviso de respuesta" : "Activar el aviso de respuesta";
      },
      // Pide el contenido una sola vez por página. HTMX procesa la página en
      // DOMContentLoaded, después de que Alpine arranca: si todavía no, se espera.
      cargar() {
        if (this.cargado) return;
        this.cargado = true;
        var contenido = this.$refs.contenido;
        var disparar = function () {
          window.setTimeout(function () { window.htmx.trigger(contenido, "cargar"); }, 0);
        };
        if (document.readyState === "loading") {
          document.addEventListener("DOMContentLoaded", disparar, { once: true });
        } else {
          disparar();
        }
      },
      alternar() {
        if (this.abierto) this.cerrar();
        else this.abrir();
      },
      abrir() {
        var self = this;
        this.abierto = true;
        this.nueva = false;
        this.anuncio = "";
        this.cargar();
        this.$nextTick(function () { self.enfocarDentro(); });
      },
      cerrar() {
        if (!this.abierto) return;
        var self = this;
        this.abierto = false;
        window.dispatchEvent(new CustomEvent("agroia-widget-cerrado"));
        this.$nextTick(function () { self.$refs.burbuja.focus(); });
      },
      cerrarConEsc() {
        this.cerrar();
      },
      enfocables() {
        var selector = "a[href], button:not([disabled]), textarea:not([disabled]), " +
          "input:not([disabled]):not([type=hidden]), [tabindex]:not([tabindex='-1'])";
        return Array.from(this.$refs.panel.querySelectorAll(selector)).filter(function (el) {
          return el.getClientRects().length > 0;
        });
      },
      enfocarDentro() {
        var campo = this.$refs.panel.querySelector("#widget-pregunta");
        if (campo) {
          campo.focus();
          return;
        }
        if (this.$refs.contenido.querySelector("[role=status] .loading")) {
          // Todavía carga: el foco espera en el panel y pasa al campo al llegar.
          this.enfocarAlCargar = true;
          this.$refs.panel.focus();
          return;
        }
        var primero = this.enfocables()[0];
        if (primero) primero.focus();
      },
      // Solo en celular (modal): Tab y Mayús+Tab no salen del panel.
      atraparFoco(evento) {
        if (!this.celular) return;
        var lista = this.enfocables();
        if (!lista.length) return;
        var primero = lista[0];
        var ultimo = lista[lista.length - 1];
        var activo = document.activeElement;
        if (evento.shiftKey && (activo === primero || activo === this.$refs.panel)) {
          evento.preventDefault();
          ultimo.focus();
        } else if (!evento.shiftKey && activo === ultimo) {
          evento.preventDefault();
          primero.focus();
        }
      },
      // Después de cada cambio de HTMX en el panel: al último mensaje, y el foco al campo
      // si se abrió mientras cargaba.
      contenidoListo() {
        var desplazable = this.$refs.contenido.querySelector("[data-desplazable]");
        if (desplazable) desplazable.scrollTop = desplazable.scrollHeight;
        if (this.enfocarAlCargar && this.abierto) {
          this.enfocarAlCargar = false;
          this.enfocarDentro();
        }
      },
      // La vista del estado manda HX-Trigger: agroia-respuesta al llegar la respuesta.
      llegoRespuesta() {
        if (!this.abierto) {
          this.nueva = true;
          this.anuncio = "AgroIA respondió. Abre el chat para ver la respuesta.";
        }
        this.sonar();
      },
      alternarSonido() {
        this.sonido = !this.sonido;
        if (this.sonido) {
          this.prepararAudio();
          this.sonar();
        }
      },
      prepararAudio() {
        if (!this.sonido) return;
        var Contexto = window.AudioContext || window.webkitAudioContext;
        if (!Contexto) return;
        if (!audioDelWidget) audioDelWidget = new Contexto();
        if (audioDelWidget.state === "suspended") audioDelWidget.resume();
      },
      // Un «pop» corto y suave (Web Audio, sin archivos), solo si el audio ya arrancó con
      // un gesto del usuario.
      sonar() {
        if (!this.sonido || !audioDelWidget || audioDelWidget.state !== "running") return;
        var ahora = audioDelWidget.currentTime;
        var oscilador = audioDelWidget.createOscillator();
        var volumen = audioDelWidget.createGain();
        oscilador.type = "sine";
        oscilador.frequency.setValueAtTime(660, ahora);
        oscilador.frequency.exponentialRampToValueAtTime(880, ahora + 0.09);
        volumen.gain.setValueAtTime(0.0001, ahora);
        volumen.gain.exponentialRampToValueAtTime(0.05, ahora + 0.015);
        volumen.gain.exponentialRampToValueAtTime(0.0001, ahora + 0.18);
        oscilador.connect(volumen).connect(audioDelWidget.destination);
        oscilador.start(ahora);
        oscilador.stop(ahora + 0.2);
      },
    };
  });

  // Dictado por voz del widget (Web Speech API). Solo si el navegador la tiene; el primer
  // uso pide aceptar el aviso (el audio lo procesa el proveedor del navegador). El texto
  // queda en el campo, sin enviarse solo. Los errores se muestran y se anuncian.
  Alpine.data("microfono", function () {
    return {
      escuchando: false,
      pidiendoPermiso: false,
      estado: "",
      error: false,
      init() {
        var self = this;
        window.addEventListener("agroia-widget-cerrado", function () { self.detener(); });
      },
      get disponible() {
        return Boolean(ReconocimientoDeVoz);
      },
      get pulsado() {
        return this.escuchando ? "true" : "false";
      },
      get etiqueta() {
        return this.escuchando ? "Dejar de escuchar" : "Dictar la pregunta por voz";
      },
      get claseBoton() {
        return this.escuchando ? "btn-error" : "btn-ghost";
      },
      get hayEstado() {
        return this.estado !== "";
      },
      get claseEstado() {
        return this.error ? "text-error" : "";
      },
      alternar() {
        if (this.escuchando) {
          this.detener();
          return;
        }
        if (!guardado(MICROFONO_ACEPTADO)) {
          this.pidiendoPermiso = true;
          return;
        }
        this.escuchar();
      },
      aceptar() {
        guardar(MICROFONO_ACEPTADO, "true");
        this.pidiendoPermiso = false;
        this.escuchar();
      },
      cancelar() {
        this.pidiendoPermiso = false;
      },
      escuchar() {
        var self = this;
        var dicto = false;
        reconocedor = new ReconocimientoDeVoz();
        reconocedor.lang = "es-MX";
        reconocedor.interimResults = false;
        reconocedor.maxAlternatives = 1;
        reconocedor.onresult = function (evento) {
          var texto = Array.from(evento.results)
            .map(function (r) { return r[0].transcript; })
            .join(" ")
            .trim();
          if (texto) {
            dicto = true;
            self.agregar(texto);
          }
        };
        reconocedor.onerror = function (evento) {
          self.fallo(evento.error);
        };
        reconocedor.onend = function () {
          self.escuchando = false;
          reconocedor = null;
          if (!self.error) self.estado = dicto ? "Listo: revisa el texto y envíalo." : "";
        };
        this.error = false;
        this.estado = "Escuchando… habla ahora.";
        this.escuchando = true;
        try {
          reconocedor.start();
        } catch (e) {
          reconocedor = null;
          this.fallo("inicio");
        }
      },
      detener() {
        if (reconocedor) reconocedor.stop();
      },
      fallo(codigo) {
        this.escuchando = false;
        if (codigo === "aborted") {
          this.estado = "";
          return;
        }
        this.error = true;
        this.estado = ERRORES_DE_VOZ[codigo] || "No pudimos usar el micrófono. Intenta de nuevo.";
      },
      agregar(texto) {
        var campo = this.$root.querySelector("textarea");
        if (!campo) return;
        campo.value = campo.value ? campo.value + " " + texto : texto;
        campo.focus();
      },
    };
  });

  // Foto del diagnóstico: vista previa antes de enviarla y validación de tipo y tamaño en el
  // navegador (el gateway lo vuelve a validar). La vista previa usa una URL blob: (CSP).
  Alpine.data("vistaPrevia", function () {
    return {
      url: "",
      error: "",
      nombre: "",
      elegir(evento) {
        var archivo = evento.target.files && evento.target.files[0];
        if (this.url) URL.revokeObjectURL(this.url);
        this.url = "";
        this.error = "";
        this.nombre = "";
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
        this.nombre = archivo.name;
      },
      // Texto del selector de archivo propio (el nativo dice «Choose File» en inglés).
      get archivoElegido() {
        return this.nombre || "Ningún archivo elegido";
      },
      get lista() {
        return this.url !== "";
      },
    };
  });

  // Selector de archivo genérico en español (componentes/campo.html): el input nativo
  // queda oculto a la vista (fuente.css, .selector-archivo) y aquí solo se muestra el nombre
  // del archivo elegido. La validación sigue en el servidor.
  Alpine.data("selectorArchivo", function () {
    return {
      nombre: "",
      url: "",
      elegir(evento) {
        if (!evento.target || evento.target.type !== "file") return;
        var archivo = evento.target.files && evento.target.files[0];
        this.nombre = archivo ? archivo.name : "";
        if (this.url) URL.revokeObjectURL(this.url);
        // Vista previa de la imagen elegida (blob:, que la CSP permite en img-src).
        this.url = archivo && archivo.type.indexOf("image/") === 0 ? URL.createObjectURL(archivo) : "";
      },
      get hayVistaPrevia() {
        return this.url !== "";
      },
      get archivoElegido() {
        return this.nombre || "Ningún archivo elegido";
      },
    };
  });

  // Confirmación con <dialog> (componentes/confirmar.html) para formularios con
  // x-data="confirmar" @submit="pedir" @htmx:confirm="pedirHtmx". Sin JavaScript el
  // formulario se envía sin confirmar. Al cerrarse, el foco vuelve al botón que lo abrió.
  Alpine.data("confirmar", function () {
    return {
      confirmado: false,
      emisor: null,
      emitir: null,
      pedir(evento) {
        // Los formularios con HTMX se confirman en htmx:confirm (pedirHtmx).
        if (this.confirmado || this.$root.hasAttribute("hx-post")) return;
        evento.preventDefault();
        this.emisor = evento.submitter || document.activeElement;
        this.$refs.dialogo.showModal();
      },
      pedirHtmx(evento) {
        if (evento.target !== this.$root) return;
        evento.preventDefault();
        this.emisor = document.activeElement;
        this.emitir = evento.detail.issueRequest;
        this.$refs.dialogo.showModal();
      },
      aceptar() {
        var emitir = this.emitir;
        var formulario = this.$root;
        var emisor = this.emisor;
        this.emitir = null;
        this.$refs.dialogo.close();
        if (emitir) {
          emitir(true);
          return;
        }
        this.confirmado = true;
        if (emisor && emisor.form === formulario) {
          formulario.requestSubmit(emisor);
        } else {
          formulario.requestSubmit();
        }
        this.confirmado = false;
      },
      cancelar() {
        this.emitir = null;
        this.$refs.dialogo.close();
      },
      cerrado() {
        if (this.emisor && document.contains(this.emisor)) this.emisor.focus();
      },
    };
  });

  // Editor de la ficha técnica del panel: filas «característica / valor» que escriben el
  // JSON en el textarea real (name="ficha_tecnica"). Sin JavaScript, o si la ficha tiene
  // listas u objetos, queda el textarea con el JSON a mano.
  Alpine.data("editorFicha", function () {
    var siguiente = 0;
    function aFila(clave, valor) {
      var tipo = typeof valor;
      var texto = tipo === "boolean" ? (valor ? "sí" : "no") : String(valor);
      siguiente += 1;
      return { indice: siguiente, clave: clave, valor: texto, tipo: tipo };
    }
    function filasDe(texto) {
      var objeto = JSON.parse(texto && texto.trim() ? texto : "{}");
      if (objeto === null || typeof objeto !== "object" || Array.isArray(objeto)) return null;
      var filas = [];
      var claves = Object.keys(objeto);
      for (var i = 0; i < claves.length; i++) {
        var valor = objeto[claves[i]];
        if (valor !== null && typeof valor === "object") return null;
        filas.push(aFila(claves[i], valor === null ? "" : valor));
      }
      return filas;
    }
    return {
      filas: [],
      modo: "json",
      error: "",
      init() {
        try {
          var filas = filasDe(this.textarea().value);
          if (filas) {
            this.filas = filas;
            this.modo = "filas";
          }
        } catch (e) {
          this.modo = "json";
        }
      },
      textarea() {
        return this.$root.querySelector("textarea[name=ficha_tecnica]");
      },
      get enFilas() {
        return this.modo === "filas";
      },
      get enJson() {
        return this.modo === "json";
      },
      get sinFilas() {
        return this.filas.length === 0;
      },
      agregar() {
        this.filas.push(aFila("", ""));
        var self = this;
        this.$nextTick(function () {
          var claves = self.$root.querySelectorAll("[data-clave]");
          if (claves.length) claves[claves.length - 1].focus();
        });
      },
      quitar(evento) {
        var indice = Number(evento.currentTarget.dataset.indice);
        this.filas = this.filas.filter(function (f) { return f.indice !== indice; });
        var self = this;
        this.$nextTick(function () { self.escribir(); });
      },
      escribir() {
        var objeto = {};
        this.$root.querySelectorAll("[data-fila]").forEach(function (fila) {
          var clave = fila.querySelector("[data-clave]").value.trim();
          var texto = fila.querySelector("[data-valor]").value.trim();
          if (!clave) return;
          var tipo = fila.dataset.tipo;
          var valor = texto;
          if (tipo === "number" && texto !== "" && !isNaN(Number(texto))) valor = Number(texto);
          if (tipo === "boolean") {
            var minusculas = texto.toLowerCase();
            if (["sí", "si", "true"].indexOf(minusculas) !== -1) valor = true;
            if (["no", "false"].indexOf(minusculas) !== -1) valor = false;
          }
          objeto[clave] = valor;
        });
        this.textarea().value = JSON.stringify(objeto, null, 2);
      },
      aJson() {
        this.escribir();
        this.error = "";
        this.modo = "json";
      },
      aFilas() {
        try {
          var filas = filasDe(this.textarea().value);
          if (!filas) {
            this.error = "Esta ficha tiene listas u objetos: edítala como JSON.";
            return;
          }
          this.filas = filas;
          this.error = "";
          this.modo = "filas";
        } catch (e) {
          this.error = "El JSON tiene un error; corrígelo para volver a la lista.";
        }
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

// Listas con desplazamiento horizontal (data-desplazar-al-foco): el elemento que recibe el
// foco se desplaza hasta quedar completo a la vista; sin animación con prefers-reduced-motion.
document.addEventListener("focusin", function (evento) {
  var lista = evento.target.closest && evento.target.closest("[data-desplazar-al-foco]");
  if (!lista) return;
  var elemento = evento.target.closest("li") || evento.target;
  var quieto = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  elemento.scrollIntoView({ block: "nearest", inline: "nearest", behavior: quieto ? "auto" : "smooth" });
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
