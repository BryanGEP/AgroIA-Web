# Entrega 3 · Gateway web

**Fecha:** 20 de noviembre de 2026 · **Entregable:** Entrega 3 · **Responsable:** Bryan Gael Esquivel Pérez

## Resumen

`web` pasó a ser el punto de entrada único del sistema:
- Guarda los JWT en la sesión del servidor y los renueva solo cuando vencen.
- Expone un proxy de API, `/api/<servicio>/<ruta>`, que valida el token antes de reenviar a usuarios, tienda, contenido o ia.
- Configura CORS solo para `/api/` y manda una Content-Security-Policy estricta, sin `unsafe-inline` ni `unsafe-eval`.
- Tiene las pantallas de cuenta: iniciar sesión, registro, verificación de correo, recuperación, mi cuenta y cambio de contraseña.

La autenticación JWT funciona de extremo a extremo y se verificó en Docker desde el navegador y a través del proxy. El carrito, el chat y el diagnóstico siguen como «Próximamente» y llegan en la siguiente fase.

## Qué se construyó

### Sesión del navegador

- **Dónde viven los tokens:** `access`, `refresh` y `usuario` (id, nombre, rol y `email_verificado`) se guardan en la sesión de Django, en `web_db`. El navegador solo recibe la cookie `sessionid`.
- **Cookie:** `HttpOnly`, `SameSite=Lax`, 7 días, y `Secure` con `DJANGO_DEBUG=False` (también la de CSRF). `cycle_key()` al iniciar sesión.
- **Cliente HTTP común (`web/clientes/api.py`):** un solo cliente httpx para los cuatro servicios, con timeout (`SERVICIOS_TIMEOUT` 10 s; `IA_TIMEOUT` 35 s, porque el agente tarda hasta 30). El cliente del catálogo se apoya en él.
- **`SesionApi`:**
  - Agrega `Authorization: Bearer <access>`.
  - Ante un 401, renueva una sola vez con el refresh y repite la petición.
  - Si la renovación falla, vacía la sesión y lanza `SesionExpirada`. `SesionExpiradaMiddleware` manda a `/iniciar-sesion/?next=<ruta>` con «Tu sesión expiró»; en HTMX, con `HX-Redirect`.
  - Si dos peticiones renuevan a la vez, la segunda adopta el par que la primera guardó en la base, en lugar de cerrar la sesión.
  - Tras renovar o cambiar la contraseña, actualiza el rol y la verificación del menú con los claims del access nuevo.
- **`X-Forwarded-For` (condición B4 de la revisión de seguridad):** el cliente común pone la `REMOTE_ADDR` de la conexión y nunca reenvía la que mande el cliente.
- **Decoradores y menú:** `@login_requerido` y `@rol_requerido("administrador")`; el context processor `usuario` alimenta el menú y el banner.

### Proxy de API y validación centralizada (`apps/proxy`)

- **Rutas:** `/api/usuarios|tienda|contenido/<ruta>` llevan a `/api/v1/<ruta>` del servicio, y `/api/ia/<ruta>` a `/<ruta>`.
- **Primera capa: el gateway valida antes de reenviar** con `agroia_comun.tokens.validar_access()` (nuevo en `comun`, sin DRF):
  - Revisa firma RS256, `JWT_ISSUER`, `exp`, `token_type == "access"` y `user_id` UUID.
  - 401 `no_autenticado` o `token_invalido` sin llegar al servicio, con `WWW-Authenticate` y registro en el log `seguridad` (`capa: gateway`).
- **Rutas públicas:** el login y el resto de la identidad (`POST`) y el catálogo (`GET`). Si traen token, se valida igual.
- **El proxy nunca toma el token de la sesión:** solo `Authorization`. Por eso no necesita CSRF; hay una prueba de que una cookie de sesión válida sin ese encabezado da 401.
- **Reenvío:**
  - Pasa método, cuerpo y query string.
  - **Encabezados de entrada (lista cerrada):** `Authorization`, `Content-Type`, `Accept` y `Accept-Language`. No pasan `Cookie`, `Host`, los de salto ni un `X-Forwarded-For` del cliente.
  - **Encabezados de salida:** `Content-Type`, `Retry-After`, `WWW-Authenticate` y `Content-Disposition`.
  - Las redirecciones del servicio se traducen a la ruta del proxy.
- **Protecciones:** rechaza servicios inexistentes y rutas con `.` o `..` (404), para que no se alcance el `/admin/` de un servicio. Responde 502 `servicio_no_disponible` o 504 `tiempo_agotado` con el formato común.
- **Segunda capa:** cada servicio sigue validando el token y decide los roles. Está documentado en [`docs/contrato-identidad.md`](../contrato-identidad.md#dos-capas-de-validación).

### CORS y encabezados de seguridad (`config/seguridad.py`)

- **CORS:** django-cors-headers 4.9.0 solo para `^/api/`. Los orígenes salen de `CORS_ALLOWED_ORIGINS` (vacío por defecto, sin comodín) y no hay credenciales cruzadas.
- **Origen no permitido:** `OrigenPermitidoMiddleware` responde 403 `origen_no_permitido` a una petición a `/api/` cuyo `Origin` no sea el del gateway ni esté en la lista. Sin `Origin` (Postman, curl) pasa.
- **Encabezados:** `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` y `X-Frame-Options: DENY`.
- **Content-Security-Policy:** `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'`.
  - **Alpine:** se cambió a `@alpinejs/csp` 3.17.4, la misma versión. Lo verifiqué contra el sha512 del paquete de npm.
  - **Código que salió del HTML:** el selector de tema y el plegado de filtros pasaron a `Alpine.data()` en `static/js/componentes.js`; el script del tema, a `static/js/tema.js`; el `hx-on` del catálogo, a un listener de `htmx:configRequest`.
  - **HTMX:** `allowEval: false` e `includeIndicatorStyles: false`. Los `style="display:none"` pasaron a `x-cloak`.
- **Excepción:** `/api/docs/` lleva una política propia, porque Swagger UI carga su código de un CDN.

### Pantallas (`apps/cuentas`)

| Ruta | Pantalla |
| --- | --- |
| `/iniciar-sesion/` | Login con `?next=` validado (solo rutas de este sitio) |
| `/registro/` | Con la casilla del aviso de privacidad |
| `/verificar-correo/?token=` | El enlace del correo: verificado, ya verificado, vencido (con botón para pedir otro) o inválido. Si hay sesión, renueva para quitar el banner |
| `/reenviar-verificacion/`, `/recuperar/` | Mensaje genérico |
| `/restablecer/<uid>/<token>/` | El enlace del correo de recuperación |
| `/mi-cuenta/` | Datos y direcciones: agregar, borrar y marcar predeterminada, con HTMX y sin JavaScript |
| `/mi-cuenta/contrasena/` | Cambio de contraseña; la sesión sigue con el par nuevo |
| `/cerrar-sesion/` | Solo `POST` con CSRF |

- **Errores:**
  - Los `campos` de la API aparecen junto a cada campo, con `aria-invalid` y `aria-describedby`, y los códigos se traducen (por ejemplo, `email_registrado`).
  - La cuenta bloqueada y el 429 tienen mensajes claros; el 429 dice cuántos segundos esperar (`Retry-After`).
- **Banner:** «Verifica tu correo para poder comprar», con botón de reenvío, cuando `email_verificado` es falso.
- **Menú:** el botón «Iniciar sesión» ya funciona. Con sesión, muestra el nombre, «Mi cuenta», «Cambiar contraseña» y «Cerrar sesión». Carrito, chat y diagnóstico siguen como «Próximamente».
- **Componentes nuevos:** `campo.html`, `errores_formulario.html`, `cerrar_sesion.html` y `banner_verificacion.html`.

### Postman

- **«Autenticación» va a través del gateway** (`{{base_gateway}}/api/usuarios/auth/login/`) y solo inicia sesión con el cliente y el administrador. `token_sin_verificar` sale de la cuenta que registra svc-usuarios, que todavía no verifica su correo.
- **Carpeta «Gateway» nueva,** que reutiliza esos tokens:
  - flujo: catálogo público, vaciar el carrito, agregar, ver y crear el pedido;
  - casos denegados: sin token y token inválido (401 del gateway), origen no permitido (403) y servicio inexistente (404).
- **Margen del límite:** una corrida hace **8 logins antes del caso del 429** (2 en «Autenticación», 1 en svc-usuarios y 5 del bloqueo), así que sobra el 20 % de los 10 por minuto. No se subieron los límites.

### Configuración y documentación

- **`docker-compose.yml`:** `CORS_ALLOWED_ORIGINS`, `SERVICIOS_TIMEOUT` e `IA_TIMEOUT` para web. Un comentario aclara que los puertos 8001 a 8005 y los de las bases son solo de desarrollo.
- **`.env.example`:** las mismas variables.
- **`CLAUDE.md`:** reglas nuevas: Alpine CSP con `Alpine.data()`, sin `hx-on` ni scripts o estilos en línea, y el proxy nunca usa la sesión.
- **`docs/requerimientos-autenticacion.md`, sección 11:** rutas en español (`/iniciar-sesion/`...) y el cliente en `web/clientes/api.py`.
- **`docs/definicion-tecnica.md`:** pantallas hechas y pendientes, la CSP, cómo viaja la identidad con el proxy, las variables nuevas, la fase 4 completa y «solo se publica web» en el plan de la Entrega 5.
- **`docs/contrato-identidad.md`:** sección «Dos capas de validación», la fila de web y los puertos solo para desarrollo.
- **READMEs:** `web/README.md` (proxy, sesión, CSP, CORS, variables) y el raíz (punto de entrada y login por el gateway).

## Decisiones técnicas

| Decisión | Por qué |
| --- | --- |
| Puertos 8001 a 8005 publicados en `127.0.0.1` solo para desarrollo; en la Entrega 5 solo se publica web | Los usan el Swagger de cada servicio, las carpetas de Postman por servicio y la depuración; quitarlos ahora cambiaría el flujo de todo el equipo |
| 403 activo para un `Origin` no permitido; sin `Origin` pasa | django-cors-headers solo omite el encabezado y deja que el navegador bloquee; el 403 también se ve fuera del navegador. Postman, curl y las apps no mandan `Origin`, y su control de acceso es el token |
| Rutas en español (`/iniciar-sesion/`, `/mi-cuenta/`) | Como las demás del sitio; se actualizó la sección 11 |
| `@alpinejs/csp` 3.17.4 | Alpine normal necesita `unsafe-eval`. La versión CSP acepta nuestras expresiones si la lógica compleja va en `Alpine.data()` |
| CSP propia en un middleware, sin django-csp | Una política fija sin nonces; Django 5.2 no trae CSP y no hacía falta otra dependencia |
| El proxy solo autentica; los roles los decide cada servicio | El proxy no conoce las reglas de negocio de cada endpoint; duplicarlas haría que se desincronizaran |
| Validación del proxy en `comun` (`tokens.validar_access`, PyJWT) | Código compartido de autenticación solo en `comun`; las clases de DRF no aplican a una vista que no es de DRF |
| Lista cerrada de encabezados en ambos sentidos | Más segura que una lista de exclusión: un encabezado nuevo no se filtra por accidente |
| Con HTMX, un formulario de direcciones con errores responde 200 | HTMX 2 no reemplaza el contenido cuando la respuesta es 4xx y el formulario con sus errores debe verse |
| `SERVICIOS_TIMEOUT` en lugar de `TIENDA_TIMEOUT` | Un solo cliente para los cuatro servicios; svc-ia tiene el suyo |

**Contradicciones resueltas con los documentos:**
- **Ruta del cliente:** la sección 11 la ponía en `web/servicios/api.py`; quedó en `web/clientes/api.py`.
- **Ruta del login:** la sección 11 decía `/login/`; quedó `/iniciar-sesion/`.
- **Alpine:** `CLAUDE.md` decía «Alpine.js 3»; sigue siendo la 3.17.4, en su versión CSP.
- **Documentación del proxy:** reenvía los contratos de los servicios, así que no lleva `@extend_schema`; se documenta en el README de web y en el contrato.

Todos los documentos se actualizaron.

## Verificación

Todo en Docker, el 20 de noviembre de 2026.

- **Navegador** (Chromium headless con Playwright 1.64.1, en `http://localhost:8000`, el host de `FRONTEND_URL`): **23 de 23 pasos correctos y 0 violaciones de la CSP o errores de JavaScript en la consola.**
  1. Registro con contraseña débil: el error aparece junto al campo («Esta contraseña es muy común.»). Luego, el registro correcto.
  2. Login con credenciales malas (mensaje genérico) y después correcto: el menú muestra el nombre y aparece el banner de correo sin verificar.
  3. La cookie de sesión es `HttpOnly` y `SameSite=Lax`, y no hay ningún JWT ni en las cookies ni en el HTML.
  4. El **enlace de verificación copiado del log** de svc-usuarios verifica el correo, y el banner desaparece.
  5. Mi cuenta: teléfono inválido con el error de la API junto al campo, datos guardados y una dirección agregada con HTMX sin recargar.
  6. Cambio de contraseña: con la actual incorrecta muestra el error; con la correcta, la sesión sigue.
  7. **Renovación automática:** cambié el access de la sesión en `web_db` por uno vencido y «Mi cuenta» cargó sin que se notara.
  8. **Sesión expirada:** con el access vencido y un refresh inválido, llevó a `/iniciar-sesion/?next=%2Fmi-cuenta%2F` con «Tu sesión expiró».
  9. Recuperación con mensaje genérico; el **enlace del log** restablece la contraseña y el login con la nueva funciona.
  10. Logout por `POST` desde el menú.
  11. El selector de tema (Alpine CSP) y los filtros del catálogo (HTMX, sin parámetros vacíos) funcionan con la CSP.
- **IP real detrás del gateway:** en el log de svc-usuarios, los logins de las pantallas aparecen con la IP `172.18.0.1` (el navegador a través de Docker), no con la del contenedor `web` (`172.18.0.9`). Así el límite por IP y el bloqueo de axes siguen funcionando.
- **Proxy:** cubierto por la carpeta «Gateway» de Postman y por las pruebas de web.
- **pytest:** **634 en verde.**

  | Servicio | Pruebas |
  | --- | --- |
  | web | 138 (antes 48) |
  | svc-usuarios | 148 |
  | svc-tienda | 147 |
  | svc-contenido | 73 |
  | svc-ia | 63 |
  | comun | 65 (antes 55) |

- **ruff:** `ruff check` y `ruff format --check` en verde en los cinco servicios, `comun` e `infra/`.
- **Postman** con Newman 6.2.1, dos corridas con 62 s de diferencia: **109 peticiones y 180 aserciones, 0 fallas en cada una.** El caso del 429 necesitó 3 vueltas (el 9.º y el 10.º login con 401, el 11.º con 429), lo que confirma que antes de él se usaron 8 de los 10 logins.
- **Capturas** en `docs/avances/img/`:
  - escritorio: `gateway-iniciar-sesion`, `gateway-registro-errores`, `gateway-banner-sin-verificar`, `gateway-correo-verificado`, `gateway-mi-cuenta`, `gateway-sesion-expirada` y `gateway-menu-con-sesion`;
  - celular (390 px): `gateway-iniciar-sesion-celular`, `gateway-registro-celular`, `gateway-mi-cuenta-celular` y `gateway-menu-celular`.

## Problemas encontrados

| Problema | Solución |
| --- | --- |
| Alpine normal y el `hx-on` del catálogo necesitan `unsafe-eval`; HTMX inyecta un `<style>` para el indicador | `@alpinejs/csp`, lógica en `static/js/`, `htmx-config` sin eval ni estilos inyectados; el CSS del indicador ya estaba en `fuente.css` |
| Una ruta del proxy con `..` podía alcanzar otras rutas del servicio | `ruta_segura()` rechaza `.`, `..` y barras invertidas (Django ya decodificó `%2e`) |
| `productos` sin barra final no era público y el servicio redirigía a su dirección interna | La expresión pública acepta la ruta sin barra y la redirección se traduce a `/api/tienda/...` |
| HTMX 2 no reemplaza el contenido con respuestas 4xx | Con HTMX, los errores del formulario de direcciones responden 200 |
| Dos peticiones simultáneas renovando con el mismo refresh cerraban la sesión | La segunda relee la sesión de la base y adopta el par nuevo |
| La captura del menú en celular salió a mitad de la animación | Se repitió esperando 800 ms |
| Docker Desktop se detuvo dos veces durante la sesión | Se volvió a iniciar; respondió en 10 s |

## Commits y Pull Requests

Rama `feat/e3-gateway` desde `develop`. Los commits se proponen al cerrar la fase.

## Pendientes y siguiente paso

- **Siguiente fase:** las pantallas de carrito y checkout, mis pedidos, chat con AgroIA, diagnóstico por imagen y el panel de administrador, sobre el cliente común y la sesión.
- **Renovación anticipada:** renovar antes de que venza el access, leyendo su `exp` (opcional en la sección 11), para ahorrar el primer 401.
- **Despliegue (Entrega 5):** solo se publica web. Si un balanceador se pone delante de web, se revisa la regla de `X-Forwarded-For`.
- **CSP:** las páginas de error de Django con `DEBUG=True` usan estilos en línea y se ven sin estilo con la CSP; solo pasa en desarrollo.
