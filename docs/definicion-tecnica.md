# AgroIA-Web · Definición técnica

Oct 22, 2026 · @bry

## Stack decidido

AgroIA-Web se construye con Django 5.2 LTS y DRF en el backend, y Tailwind + daisyUI + HTMX + Alpine en las plantillas del gateway. Todo corre localmente con Docker Compose.

| Capa | Tecnología | Versión | Para qué |
| --- | --- | --- | --- |
| Lenguaje | Python | 3.12 | Todos los servicios |
| Framework | Django | 5.2 LTS | Gateway y microservicios. Es LTS con soporte hasta abril de 2028; la 6.0 ya salió de soporte principal |
| API | Django REST Framework | última estable | Endpoints REST de cada servicio |
| Documentación API | drf-spectacular | última estable | Swagger / OpenAPI en `/api/docs/` |
| Filtros | django-filter | última estable | Filtros y ordenamiento de listados |
| Autenticación | djangorestframework-simplejwt + django-axes | última estable | JWT, blacklist y bloqueo por intentos |
| Base relacional | PostgreSQL | 16 | Usuarios, catálogo y pedidos |
| Base de documentos | MongoDB + pymongo | 7 | Conversaciones, diagnósticos y bitácora |
| Caché / mensajería | Redis | 7 | Throttling ahora; eventos en la Entrega 4 |
| Servicio de IA | FastAPI | la del repo AgroIA | Adaptador del agente (contenedor `agente` del repo AgroIA, LangChain + Groq) y modelo de visión |
| Estilos | Tailwind CSS + daisyUI | 4.x + 5.x | Diseño y componentes, sin Node con `django-tailwind-cli` |
| Interactividad | HTMX + django-htmx | 2.x | Actualizar partes de la página sin recargar |
| Interactividad ligera | Alpine.js | 3.x | Menús, modales, vista previa de imágenes |
| Pruebas | pytest + pytest-django | última estable | Pruebas unitarias y de endpoints |
| Estilo de código | ruff | última estable | Linter y formateador |
| Contenedores | Docker + Docker Compose | actual | Levantar todo con `docker compose up` |

Las versiones "última estable" se fijan en el `requirements.txt` de cada servicio el día que se crea. Nada de Node.js: `django-tailwind-cli` descarga el ejecutable de Tailwind con daisyUI incluido.

Fuentes: [ciclo de soporte de Django](https://versionlog.com/django/), [django-tailwind-cli](https://pypi.org/project/django-tailwind-cli/4.8.1/), [daisyUI sin Node](https://daisyui.com/docs/install/standalone/).

## Arquitectura

&#91;embedded content: arquitectura de AgroIA-Web · gateway, 4 servicios y sus datos\]

El gateway es el único punto de entrada: recibe al navegador y reparte cada petición al servicio que corresponde con el JWT del usuario. Ningún servicio lee la base de otro.

## Servicios

Son cinco servicios propios, el contenedor `agente` (construido desde el repo AgroIA) y tres de infraestructura. Catálogo y pedidos se juntan en `svc-tienda`, y agente y diagnóstico en `svc-ia`, para no mantener seis servicios en cuatro semanas.

| Servicio | Responsabilidad | Base de datos | Puerto local | Pieza del maestro |
| --- | --- | --- | --- | --- |
| `web` | Gateway: plantillas, sesión, enruta al resto y valida JWT (Entrega 3) | sesiones en PostgreSQL `web_db` | 8000 | API Gateway |
| `svc-usuarios` | Registro, login, JWT, recuperación, roles, perfil y direcciones | PostgreSQL `usuarios_db` | 8001 | Identidad y usuarios |
| `svc-tienda` | Categorías, productos, stock, carrito y pedidos | PostgreSQL `tienda_db` | 8002 | Negocio principal |
| `svc-contenido` | Conversaciones con el agente, historial de diagnósticos y bitácora de actividad | MongoDB `contenido` | 8003 | Datos no estructurados |
| `svc-ia` | Adaptador: traduce el contrato al agente y clasifica imágenes de aguacate (modelo pendiente) | ninguna | 8004 | Integración de IA |
| `agente` | Agente conversacional del repo BryanGEP/AgroIA, construido desde GitHub (`main:svc-agente`). Solo red interna | ninguna | 8005 (solo pruebas) | — |
| `postgres` | Un contenedor con una base por servicio | — | 5432 | — |
| `mongo` | Base de documentos | — | 27017 | — |
| `redis` | Caché para throttling; eventos en la Entrega 4 | — | 6379 | — |

**Reglas entre servicios:**

- El navegador solo habla con `web`. Ningún servicio interno se publica hacia afuera.
- Cada servicio es dueño de su base: nadie lee la base de otro. Si necesita un dato, llama a su API.
- En la Entrega 2 las llamadas entre servicios son HTTP síncronas. En la Entrega 4, guardar conversaciones y diagnósticos en `svc-contenido` pasa a ser un evento por Redis.
- Dentro de Docker, los servicios se llaman por su nombre: `http://svc-tienda:8000`. El puerto local solo sirve para probar desde la computadora.

## Estructura del monorepo

Cada servicio es un proyecto independiente con su propio `requirements.txt`, `Dockerfile` y pruebas. Lo compartido vive en `comun/` y se instala en cada servicio como paquete local.

```text
AgroIA-Web/
├── CLAUDE.md                 # reglas para Claude Code
├── README.md
├── CONTRIBUTING.md
├── docker-compose.yml
├── .env.example
├── .github/
├── docs/                     # entregables y documentación
├── infra/                    # postgres/init.sql, generar_llaves.py
├── comun/                    # paquete compartido: auth JWT, permisos, errores
│   ├── pyproject.toml
│   └── agroia_comun/
│       ├── autenticacion.py
│       ├── permisos.py
│       └── errores.py
├── web/                      # gateway con plantillas
├── svc-usuarios/
├── svc-tienda/
├── svc-contenido/
└── svc-ia/                   # FastAPI
```

Estructura interna de un servicio Django (ejemplo `svc-tienda`):

```text
svc-tienda/
├── Dockerfile
├── requirements.txt          # dependencias de ejecución
├── requirements-dev.txt      # pytest, ruff, factory-boy
├── pytest.ini
├── manage.py
├── config/                   # proyecto Django
│   ├── settings.py           # lee todo de variables de entorno
│   └── urls.py               # /api/v1/, /api/docs/, /salud/
└── apps/
    ├── catalogo/
    │   ├── models.py
    │   ├── serializers.py
    │   ├── views.py          # ViewSets
    │   ├── filters.py
    │   ├── urls.py
    │   ├── admin.py
    │   └── tests/
    └── pedidos/
```

El gateway `web/` sigue la misma base, con `templates/` (una carpeta por módulo y `parciales/` para los fragmentos que devuelve HTMX), `static/css/fuente.css` (entrada de Tailwind) y `clientes/` (un cliente HTTP por servicio).

El agente vive en el repo AgroIA y sigue evolucionando ahí; no se copia su código. Docker Compose construye el contenedor `agente` desde `https://github.com/BryanGEP/AgroIA.git#main:svc-agente` y `svc-ia` lo llama por HTTP, traduciendo el contrato de AgroIA-Web a la API del agente (`POST /chat`). Los cambios del agente se hacen en AgroIA.

## Contratos de API

Todos los servicios exponen `/api/v1/...`, documentación en `/api/docs/` y un `GET /salud/` que responde `{"estado": "ok"}` para Docker. Los listados usan paginación `?page=` con 20 elementos.

**Formato de errores** (manejador común en `comun/agroia_comun/errores.py`): `{"error": "codigo_corto", "detalle": "mensaje para el usuario"}`. Los errores de validación agregan `"campos"` con los mensajes por campo:

```json
{"error": "validacion", "detalle": "Revisa los datos enviados.",
 "campos": {"direccion_envio": {"codigo_postal": ["El código postal debe tener 5 dígitos."]}}}
```

| Código | HTTP | Cuándo |
| --- | --- | --- |
| `validacion` | 400 | Datos inválidos; trae `campos`. En el registro, los casos propios llegan como mensaje del campo: `email` → `email_registrado`, `password_confirmacion` → `password_no_coincide`, `acepto_privacidad` → `privacidad_no_aceptada` |
| `json_invalido` | 400 | El cuerpo no es JSON válido |
| `no_autenticado` | 401 | Falta el token |
| `token_invalido` | 401 | Token con firma, emisor o tipo incorrectos, o vencido |
| `sin_permiso` | 403 | Rol equivocado o correo sin verificar |
| `no_encontrado` | 404 | No existe, o no es del usuario (no se revela que existe) |
| `metodo_no_permitido` | 405 | Método HTTP no soportado en esa ruta |
| `carrito_vacio` | 400 | Se intenta crear un pedido sin productos en el carrito |
| `stock_insuficiente` | 409 | La cantidad pedida supera el stock disponible |
| `producto_no_disponible` | 409 | El producto o su categoría están desactivados |
| `transicion_invalida` | 409 | Cambio de estado del pedido no permitido |
| `conversacion_llena` | 409 | La conversación llegó a 200 mensajes; hay que iniciar otra |
| `agente_no_disponible` | 503 | El agente no respondió, falló o tardó más que `AGENTE_TIMEOUT` (svc-ia) |
| `modelo_no_disponible` | 503 | No hay modelo de visión configurado; se integra en una entrega posterior (svc-ia) |

Los códigos de negocio (`carrito_vacio` en adelante) se lanzan con `ErrorDeNegocio` desde `servicios.py`; svc-ia, que no usa `comun`, produce los suyos con el mismo formato. Un ObjectId mal formado en svc-contenido responde `no_encontrado` (404), igual que uno inexistente o ajeno.

**`svc-usuarios`** — detalle completo en el documento de requerimientos de autenticación.

| Método | Ruta | Acceso |
| --- | --- | --- |
| POST | `/auth/registro/` | público. Responde `{"id", "email", "mensaje"}`, sin tokens. **Entrega 2** |
| POST | `/auth/login/`, `/auth/token/renovar/` | público (Entrega 3) |
| POST | `/auth/verificar-correo/`, `/auth/reenviar-verificacion/` | público (Entrega 3) |
| POST | `/auth/recuperar/`, `/auth/restablecer/` | público (Entrega 3) |
| POST | `/auth/logout/`, `/auth/cambiar-password/` | autenticado (Entrega 3) |
| GET, PATCH | `/usuarios/yo/` | autenticado. Solo se editan `nombre`, `apellidos` y `telefono`. **Entrega 2** |
| CRUD | `/usuarios/yo/direcciones/` | autenticado, solo las propias (también el administrador). Una sola predeterminada. **Entrega 2** |
| GET | `/usuarios/` | administrador. Filtros `rol` y `q`. **Entrega 2** |
| PATCH | `/usuarios/<id>/rol/` | administrador (Entrega 3; en la Entrega 2 se usa el comando `asignar_admin <email>`) |

**`svc-tienda`**

| Método | Ruta | Acceso | Notas |
| --- | --- | --- | --- |
| GET | `/categorias/` | público |  |
| POST, PATCH, DELETE | `/categorias/...` | administrador | Borrado lógico (`activa=False`) |
| GET | `/productos/` | público | Filtros: `categoria`, `precio_min`, `precio_max`, `disponible`, `q` (búsqueda). Orden: `precio`, `nombre`, `creado_en` |
| GET | `/productos/<slug>/` | público |  |
| POST, PATCH, DELETE | `/productos/...` | administrador | Borrado lógico (`activo=False`) |
| GET, DELETE | `/carrito/` | autenticado | Ver o vaciar. Un carrito por usuario; se crea al primer uso |
| POST | `/carrito/items/` | autenticado | `{"producto": "<slug>", "cantidad"}`. Si ya está, suma; valida stock |
| PATCH, DELETE | `/carrito/items/<id>/` | autenticado | Cambiar cantidad o quitar |
| POST | `/pedidos/` | cliente con correo verificado | Recibe `direccion_envio` y `metodo_pago` (`tarjeta`, `transferencia`, `contra_entrega`; todos simulados). Convierte el carrito en pedido, valida y descuenta stock en una transacción. Envío `COSTO_ENVIO`, gratis si el subtotal supera `ENVIO_GRATIS_DESDE` |
| GET | `/pedidos/`, `/pedidos/<id>/` | dueño o administrador |  |
| POST | `/pedidos/<id>/pagar/` | cliente dueño | Pago simulado: `pendiente → pagado`; responde `"pago_simulado": true`. Agregado en la fase 2 |
| PATCH | `/pedidos/<id>/estado/` | administrador | `pendiente → pagado → enviado → entregado`, o `cancelado` desde `pendiente` o `pagado`; al cancelar se devuelve el stock |

**`svc-contenido`**

| Método | Ruta | Acceso |
| --- | --- | --- |
| GET, POST | `/conversaciones/` | autenticado (solo las propias; también el administrador) |
| GET, DELETE | `/conversaciones/<id>/` | dueño (las conversaciones son privadas: el administrador recibe 404) |
| POST | `/conversaciones/<id>/mensajes/` | dueño. `{"rol": "usuario" \| "agente", "texto", "fuentes"?}`; máximo 200 mensajes (`conversacion_llena`) |
| GET, POST | `/diagnosticos/` | autenticado (solo los propios; el administrador lista todos). POST en `multipart`: imagen JPG, PNG o WebP (máx. 5 MB) y el resultado de svc-ia |
| GET | `/diagnosticos/<id>/` | dueño o administrador |
| GET, POST | `/bitacora/` | administrador. Filtros `tipo`, `desde`, `hasta`. POST manual por ahora; en la Entrega 4 la llenan los eventos |

**`svc-ia`** — diseñado desde ahora para volverse asíncrono en la Entrega 4: cada respuesta trae `id` y `estado`.

| Método | Ruta | Recibe | Devuelve |
| --- | --- | --- | --- |
| POST | `/agente/preguntar/` | `{"pregunta", "historial": [...]}` | `{"id", "estado": "listo", "respuesta", "fuentes"}` |
| POST | `/diagnostico/` | imagen `multipart`, máx. 5 MB, JPG o PNG | `{"id", "estado": "listo", "clase": "sano" \| "rona" \| "antracnosis", "confianza": 0.0–1.0, "probabilidades", "modelo_version"}`. **Entrega 2: 503 `modelo_no_disponible`**, el modelo de visión todavía no existe |
| GET | `/solicitudes/<id>/` | — | Estado de una solicitud (dueño o administrador); en la Entrega 2 siempre `listo`, guardada en memoria (pasa a Redis en la Entrega 4) |

`historial` es una lista de `{"rol": "usuario" | "agente", "texto"}`; svc-ia envía al agente las últimas 10 entradas como contexto y un `session_id` nuevo por petición. `fuentes` llega vacío hasta que el agente tenga RAG. Si el agente falla: 503 `agente_no_disponible`.

En la Entrega 2, svc-ia y svc-contenido no se llaman entre sí: `web` llama a `svc-ia` y después guarda el resultado en `svc-contenido`. En la Entrega 4, `svc-ia` responderá `estado: "pendiente"` y publicará el resultado como evento.

## Modelo de datos

PostgreSQL guarda lo que necesita integridad y transacciones (usuarios, stock, pedidos). MongoDB guarda lo que crece y cambia de forma (mensajes, resultados de IA, bitácora). Entre servicios no hay llaves foráneas: se guarda el `usuario_id` como entero.

**PostgreSQL · `usuarios_db`**

| Tabla | Campos principales |
| --- | --- |
| `Usuario` | `AbstractUser` sin `username`; `email` (único, es el login), `nombre`, `apellidos`, `telefono`, `rol`, `email_verificado`, `token_version`, `acepto_privacidad_en`, `version_privacidad`, `tiene_2fa`. `AUTH_USER_MODEL = "usuarios.Usuario"`; su `id` es el `user_id` del JWT |
| `Direccion` | `usuario` FK, `alias`, `calle`, `numero`, `colonia`, `municipio`, `estado`, `codigo_postal`, `referencias`, `predeterminada` (una sola por usuario, con `UniqueConstraint` condicional), `creada_en` |
| `Dispositivo2FA`, `CodigoRespaldo` | Ver sección 12 del documento de autenticación |

**PostgreSQL · `tienda_db`**

| Tabla | Campos principales |
| --- | --- |
| `Categoria` | `nombre`, `slug` (único), `descripcion`, `activa` |
| `Producto` | `categoria` FK, `nombre`, `slug` (único), `descripcion`, `precio` (Decimal 10,2), `stock` (≥ 0), `unidad` (pieza, kg, litro, costal), `imagen`, `ficha_tecnica` (JSON: dosis, composición, etc.), `activo`, `creado_en` |
| `Carrito` | `usuario_id`, `creado_en`, `actualizado_en` |
| `ItemCarrito` | `carrito` FK, `producto` FK, `cantidad` (> 0); único por carrito y producto |
| `Pedido` | `usuario_id`, `estado`, `direccion_envio` (JSON, copia al momento de comprar), `subtotal`, `envio`, `total`, `metodo_pago`, `creado_en` |
| `ItemPedido` | `pedido` FK, `producto` FK, `nombre_producto` y `precio_unitario` (copias), `cantidad`, `importe` |

Los pedidos copian el nombre, el precio y la dirección: si después cambian, el pedido conserva lo que se compró. La ficha técnica variable va como `JSONField` en PostgreSQL para no repartir un producto entre dos bases.

**MongoDB · `contenido`**

```json
// conversaciones
{ "_id": ObjectId, "usuario_id": 12, "titulo": "Manchas en hojas",
  "creada_en": ISODate, "actualizada_en": ISODate,
  "mensajes": [ { "rol": "usuario", "texto": "...", "fecha": ISODate },
                { "rol": "agente", "texto": "...", "fuentes": ["..."], "fecha": ISODate } ] }

// diagnosticos
{ "_id": ObjectId, "usuario_id": 12, "imagen": "diagnosticos/<uuid>.png",
  "clase": "antracnosis", "confianza": 0.91,
  "probabilidades": { "sano": 0.03, "rona": 0.06, "antracnosis": 0.91 },
  "modelo_version": "v1", "creado_en": ISODate }

// bitacora
{ "_id": ObjectId, "tipo": "pedido_creado", "usuario_id": 12,
  "servicio": "svc-tienda", "datos": { ... }, "fecha": ISODate }
```

Índices: `usuario_id` + `actualizada_en` en conversaciones, `usuario_id` + `creado_en` en diagnósticos, `tipo` + `fecha` y `fecha` en bitácora; los crea `python manage.py crear_indices` al arrancar el contenedor. En diagnósticos se guarda el nombre del archivo en `default_storage` (`imagen`) y la API calcula `imagen_url`, para que siga funcionando al pasar a Cloud Storage. Los mensajes van dentro de su conversación porque siempre se leen juntos; si una conversación pasa de 200 mensajes, se inicia otra.

## Frontend

El gateway renderiza HTML con plantillas de Django. daisyUI da los componentes, Tailwind ajusta el diseño, HTMX actualiza partes de la página y Alpine maneja lo que solo pasa en el navegador.

**Quién hace qué:**

| Necesidad | Herramienta | Ejemplo en AgroIA-Web |
| --- | --- | --- |
| Componente estándar | daisyUI | `btn btn-primary`, `card`, `navbar`, `modal`, `alert`, `badge`, `input` |
| Ajuste de diseño | Tailwind | `grid md:grid-cols-3 gap-6`, `max-w-6xl mx-auto` |
| Algo cambia con datos del servidor | HTMX | Enviar pregunta al agente, agregar al carrito, filtrar productos, paginar |
| Algo cambia solo en el navegador | Alpine | Abrir un menú, vista previa de la imagen antes de subirla, mostrar u ocultar contraseña |

**Reglas:**

1. **Tema propio de daisyUI** llamado `agroia` en `static/css/fuente.css`: primario verde aguacate, secundario café tierra, fondo claro. Modo oscuro opcional con el tema `agroia-oscuro`.
2. **Plantilla base única** (`templates/base.html`) con navbar, mensajes de Django como `alert` y pie con el aviso de privacidad. Todas las páginas la extienden.
3. **Fragmentos para HTMX** en `templates/<modulo>/parciales/_nombre.html`. La vista revisa `request.htmx` (django-htmx): si es petición HTMX devuelve el parcial; si no, la página completa.
4. **CSRF en HTMX:** en `base.html`, `<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>`.
5. **Componentes repetidos como `{% include %}`** con parámetros, en `templates/componentes/`: tarjeta de producto, campo de formulario, paginador, estado vacío.
6. **Indicadores de carga** en toda petición HTMX que tarde: `hx-indicator` con un `loading` de daisyUI. El agente y el diagnóstico pueden tardar varios segundos.
7. **Responsive desde el inicio:** primero celular, después `md:` y `lg:`. Muchos productores van a entrar desde el teléfono.
8. **HTMX y Alpine se sirven desde `static/vendor/`**, no desde un CDN, para que funcione sin internet en la demo. Las fuentes (Barlow y Barlow Semi Condensed, OFL) también son locales, en `static/fonts/`.
9. **Accesibilidad mínima:** cada `input` con `label`, imágenes con `alt`, contraste del tema revisado.
10. **Imágenes de otros servicios:** el navegador no alcanza las direcciones internas. El gateway reescribe las URLs de imagen de svc-tienda a `/media/tienda/<ruta>` y esa ruta reenvía el archivo (solo `productos/` e `image/*`), sin publicar svc-tienda. Con Cloud Storage (Entrega 5) las URLs serán públicas y no se reescriben.
11. **CSS compilado:** `static/css/agroia.css` se genera a partir de `fuente.css` y no se sube al repo; el contenedor `web` lo compila al arrancar.

**Base visual hecha** (ver `docs/avances/web-base-catalogo.md`): temas `agroia` y `agroia-oscuro`, `base.html`, componentes, inicio, catálogo con filtros HTMX que también funciona sin JavaScript, detalle y aviso de privacidad.

**Pantallas de la Entrega 2:** inicio, catálogo con filtros, detalle de producto, carrito, checkout, mis pedidos, chat con AgroIA, diagnóstico por imagen con historial, registro, login, recuperar contraseña, perfil con direcciones, y panel de administrador para productos y pedidos.

## Autenticación

La implementa el equipo en `svc-usuarios` desde ahora; después se adaptará al módulo que arma el grupo. El detalle de cada tarea está en [AgroIA-Web · Requerimientos de autenticación](https://claude.ai/code/artifact/27b14141-4c7a-4e47-a6a4-53796b9db979).

**Cómo viaja la identidad:**

1. El usuario inicia sesión en `web`. El gateway llama a `svc-usuarios`, recibe access y refresh, y los guarda en su sesión de servidor.
2. El navegador solo recibe la cookie de sesión de Django (`HttpOnly`).
3. En cada petición, el gateway reenvía `Authorization: Bearer <access>` al servicio que corresponda.
4. Cada servicio valida la firma RS256 con la llave pública, sin consultar `svc-usuarios`, y lee `user_id`, `rol` y `email_verificado` del token.
5. Si el access venció, el gateway renueva con el refresh y repite la petición.

**Adaptación para que no estorbe en la Entrega 2:** las clases de autenticación y permisos se escriben una vez en `comun/` (implementadas en la fase 2) y se controlan con la variable `AUTH_ACTIVA`. Con `True`, aplican JWT y roles. Con `False` se apagan solo las revisiones de rol: un token que llega se valida igual, y los endpoints que necesitan saber quién es el usuario (carrito, pedidos) responden 401 sin token. Para desarrollo, los tokens se generan con `infra/emitir_token.py`. Su valor por defecto en el código es `True`; solo el `.env` local puede apagarla, y solo junto con `DJANGO_DEBUG=True` (si no, el servicio no arranca). Para la entrega debe estar en `True`.

Antes de cerrar la parte de autenticación, revisarla con las skills `insecure-defaults` y `static-analysis` de Claude Code.

## Entorno local

Todo el sistema se levanta con `docker compose up --build` desde la raíz. Cada servicio escucha en el puerto 8000 dentro de su contenedor y se publica en su puerto local (8000–8004).

**`docker-compose.yml` debe incluir:**

- Los nueve contenedores de la tabla de servicios (incluido `agente`), en una red interna común.
- `postgres` con un script en `infra/postgres/init.sql` que crea `usuarios_db`, `tienda_db` y `web_db` (sesiones del gateway), cada una con su propio usuario (`usuarios`, `tienda`, `web`). Las contraseñas no van en el script: psql las lee del entorno con `\getenv`. Solo corre la primera vez que se crea el volumen; para repetirlo, `docker compose down -v` (borra los datos).
- Volúmenes con nombre para PostgreSQL y MongoDB, para no perder datos al reiniciar.
- Puertos publicados solo en `127.0.0.1` (también los de las bases): sirven para probar desde la computadora y no quedan visibles en la red.
- `healthcheck` en las bases y `depends_on: condition: service_healthy` en los servicios que las usan.
- Código montado como volumen en desarrollo, para que los cambios se vean sin reconstruir la imagen.
- Al arrancar cada servicio Django: `python manage.py migrate` y luego el servidor.

**Variables de entorno** (un solo `.env` en la raíz, documentado en `.env.example`):

| Variable | Ejemplo | Usada por |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | cadena aleatoria larga | servicios Django |
| `DJANGO_DEBUG` | `True` en local | servicios Django |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,web,svc-usuarios,...` | servicios Django |
| `AUTH_ACTIVA` | `True` | todos |
| `POSTGRES_HOST`, `POSTGRES_PORT` | `postgres`, `5432` | usuarios, tienda, web |
| `POSTGRES_SUPERUSER_PASSWORD` | contraseña de desarrollo | contenedor `postgres` |
| `USUARIOS_DB_PASSWORD`, `TIENDA_DB_PASSWORD`, `WEB_DB_PASSWORD` | contraseña de desarrollo | `init.sql` y cada servicio |
| `MONGO_URL` | `mongodb://mongo:27017/contenido` | svc-contenido |
| `REDIS_URL` | `redis://redis:6379/0` | usuarios, web |
| `JWT_PRIVATE_KEY_PATH` / `JWT_PUBLIC_KEY_PATH` | `/run/secrets/jwt_privada.pem` / `/run/secrets/jwt_publica.pem` | usuarios / todos |
| `URL_SVC_USUARIOS`, `URL_SVC_TIENDA`, `URL_SVC_CONTENIDO`, `URL_SVC_IA` | `http://svc-tienda:8000` | web |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | backend de consola en local | svc-usuarios |
| `FRONTEND_URL` | `http://localhost:8000` | svc-usuarios (enlaces de correo) |
| `VERSION_AVISO_PRIVACIDAD` | `2026-10` | svc-usuarios (versión del aviso que se guarda al registrarse) |
| `COSTO_ENVIO`, `ENVIO_GRATIS_DESDE` | `150.00`, `1500.00` | svc-tienda |
| `GROQ_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL` | llave propia de cada integrante, `groq`, `openai/gpt-oss-120b` | contenedor `agente` |
| `URL_AGENTE`, `AGENTE_TIMEOUT` | `http://agente:8000`, `30` | svc-ia |

Cada servicio Django recibe en su contenedor `POSTGRES_DB`, `POSTGRES_USER` y `POSTGRES_PASSWORD` con los de su propia base; `docker-compose.yml` los traduce desde las variables de arriba, y cada contenedor recibe solo las variables que usa.

Las llaves `.pem` viven en `infra/llaves/`, que está en `.gitignore`. El script `infra/generar_llaves.py` (Python con `cryptography`, funciona igual en Windows y Linux, sin `openssl`) las crea la primera vez y nunca las sobrescribe. `docker-compose.yml` las monta como *secrets* en `/run/secrets/`: la pública en todos los servicios y la privada solo en `svc-usuarios`.

**Comandos del día a día:**

```bash
docker compose up --build                       # levantar todo
docker compose exec svc-tienda pytest           # pruebas de un servicio
docker compose exec svc-tienda python manage.py makemigrations
docker compose exec web python manage.py tailwind build
docker compose logs -f svc-ia                   # ver logs de un servicio
```

## Convenciones de código, pruebas y documentación

El código se escribe en español (modelos, campos, variables, URLs, mensajes) sin acentos ni ñ en los identificadores: `Direccion`, `rona`, `anio`. Los nombres propios de Django y DRF se quedan en inglés (`models`, `serializers`, `get_queryset`).

**Código:**

- `ruff check` y `ruff format` pasan antes de cada commit; configuración única en `ruff.toml` en la raíz, línea de 100 caracteres.
- Vistas con `ViewSet` + `router` para CRUD; `APIView` solo para acciones que no son CRUD (login, crear pedido).
- La lógica de negocio va en `servicios.py` de cada app, no en las vistas ni en los serializers. Ejemplo: `crear_pedido_desde_carrito(usuario_id)`.
- Toda operación que toca stock o dinero va en `transaction.atomic()` y usa `select_for_update()` sobre los productos.
- Dinero siempre en `Decimal`, nunca `float`.
- Nada de secretos en el código: todo sale de variables de entorno.
- Docstring corto en funciones de `servicios.py` y en endpoints no obvios.

**Pruebas** (`pytest` + `pytest-django` + `factory-boy`):

- Cada app tiene `tests/` con `test_modelos.py`, `test_endpoints.py` y, si aplica, `test_servicios.py`.
- Por cada endpoint: el caso correcto, una validación que falla y, con `AUTH_ACTIVA`, el acceso sin token (401) y con rol equivocado (403).
- Las llamadas a otros servicios y al LLM se simulan con `responses` o `unittest.mock`; las pruebas no dependen de que otro contenedor esté arriba.
- `svc-contenido` usa `mongomock` en pruebas.
- Meta: las pruebas de un servicio corren en menos de 30 segundos.

**Documentación:**

- `drf-spectacular` genera Swagger en `/api/docs/`; cada serializer y endpoint tiene descripción y ejemplos con `@extend_schema`. `svc-ia` usa el Swagger que trae FastAPI.
- Cada servicio tiene su `README.md`: qué hace, variables que usa, cómo correr pruebas y su matriz de endpoints × rol.
- Colección de Postman en `docs/postman/AgroIA-Web.postman_collection.json`, con un entorno `local` y una carpeta por servicio. Se actualiza en el mismo PR que agrega un endpoint.

**Ramas y commits:** igual que en `CONTRIBUTING.md`. Un PR por historia; el PR no se fusiona si fallan `ruff` o `pytest`.

## Trabajo con Claude Code

Un `CLAUDE.md` en la raíz resume este documento en reglas que Claude Code lee al iniciar cada sesión, para que los tres obtengan código con la misma estructura. Cada servicio puede tener su propio `CLAUDE.md` corto con lo específico (por ejemplo, `svc-ia` explica cómo cargar el modelo de visión).

**Forma de trabajar una historia:**

1. Crear la rama desde `develop` (`feat/...`).
2. Pedirle a Claude Code un plan antes de código, con la skill de planeación de *superpowers*. Revisar el plan y corregirlo.
3. Implementar con pruebas primero (skill de TDD de *superpowers*) para la lógica de negocio y los endpoints.
4. Correr `ruff` y `pytest` dentro del contenedor del servicio.
5. Revisar el diff completo y hacer el commit y el push a mano. Claude Code no hace commits ni push en este proyecto, y quien hace el PR es responsable del código.

**Skills por tipo de tarea:**

| Tarea | Skill |
| --- | --- |
| Planear una historia o un servicio nuevo | `superpowers` (brainstorming, writing-plans) |
| Lógica de negocio y endpoints | `superpowers` (test-driven-development) |
| Pantallas y componentes | `frontend-design`, `web-design-guidelines` |
| Probar pantallas en un navegador | `webapp-testing` (example-skills) |
| Revisar autenticación y configuración | `insecure-defaults`, `static-analysis` |
| Revisar un PR grande | `differential-review` |
| Revisar dependencias nuevas | `supply-chain-risk-auditor` |
| Documentos de entrega | `docx`, `pdf` |

`vercel-react-best-practices` no aplica, porque no se usa React.

**Contexto que conviene darle a Claude Code** en cada tarea: el servicio y la historia, el contrato del endpoint de este documento y qué debe quedar probado. Pedidos vagos como "haz el carrito" producen código que no respeta los contratos.

## Plan de construcción

La fase 0 la hace una sola persona porque todo depende de ella. Después, las fases 1, 2 y 3 pueden ir en paralelo, una por integrante. Jira se documenta al final, como acordó el equipo.

1. **Fase 0 · Base del monorepo.** `CLAUDE.md`, `ruff.toml`, `docker-compose.yml`, `.env.example`, script de llaves, init de PostgreSQL, paquete `comun/` vacío y el esqueleto de los cinco servicios respondiendo `GET /salud/`. Termina cuando `docker compose up` levanta todo en verde.
2. **Fase 1 · Usuarios y entrada.** Para la Entrega 2 se hizo la versión básica: modelo `Usuario` y `Direccion`, registro con aviso de privacidad, perfil, direcciones, listado del administrador y comando `asignar_admin`; lo demás pasa a la Entrega 3. En `svc-usuarios`: modelo `Usuario`, envío de correos, registro, verificación, login, renovación, logout, aviso de privacidad, perfil y direcciones. En `web`: Tailwind + daisyUI, tema `agroia`, `base.html` y pantallas de registro, login y perfil.
3. **Fase 2 · Tienda.** Modelos, CRUD con filtros, búsqueda y paginación, carrito y creación de pedidos con stock. Se adelantó aquí la validación RS256 en `comun/` (autenticación, permisos y formato de errores) y el script `infra/emitir_token.py`. Pantallas de catálogo, detalle, carrito, checkout, mis pedidos y panel de administrador.
4. **Fase 3 · IA y contenido.** `svc-ia` como adaptador del agente del repo AgroIA (contenedor `agente`) y con la interfaz del clasificador (el modelo de visión llega en una entrega posterior); `svc-contenido` con conversaciones, diagnósticos y bitácora. Pantallas de chat y de diagnóstico con historial.
5. **Fase 4 · Seguridad completa.** Recuperación y cambio de contraseña, roles y permisos en el resto de los servicios (la validación RS256 de `comun/` ya existe desde la fase 2), revisión de `token_version`, límite de intentos, sesión del gateway y `AUTH_ACTIVA=True`. 2FA y los opcionales solo si sobra tiempo.
6. **Fase 5 · Calidad y entrega.** Completar pruebas, Swagger con ejemplos, colección de Postman, READMEs de cada servicio y revisión con `insecure-defaults` y `static-analysis`.
7. **Fase 6 · Jira.** Cargar historias, sprints y retrospectivas con lo que realmente se hizo.

## Decisiones tomadas

El equipo aprobó estas decisiones el 22 de octubre de 2026. En el documento de la Entrega 2 van en una sección de "ajustes a la arquitectura" respecto al Entregable 1.

| Decisión | Qué se hace | Por qué |
| --- | --- | --- |
| Servicios fusionados | Catálogo y pedidos en `svc-tienda`; agente y diagnóstico en `svc-ia` | Crear un pedido descuenta stock en la misma transacción; separarlos obligaría a una transacción distribuida. Agente y visión comparten dependencias y despliegue |
| Ficha técnica | `JSONField` en PostgreSQL | MongoDB queda para conversaciones, diagnósticos y bitácora, que son los datos que realmente crecen y cambian de forma |
| `svc-ia` | FastAPI como adaptador: el agente corre en su propio contenedor, construido desde el repo AgroIA, y svc-ia traduce el contrato (decisión revisada en la fase 3) | El agente sigue evolucionando en su repo sin copias que se desincronicen. Valida el JWT con PyJWT, porque las clases de `comun/` son de DRF |
| Proveedor del LLM | El que ya usa el agente | Llave solo en `.env` y límite de gasto en la cuenta del proveedor |
| Pago | Simulado: botón "Pagar" que marca el pedido como `pagado`, con etiqueta visible "pago simulado" | Ninguna entrega califica pagos |
| Imágenes | Volumen local, siempre con `STORAGES` y `default_storage` de Django, nunca rutas a mano | En la Entrega 5 se pasa a Cloud Storage con `django-storages` cambiando solo la configuración. Las imágenes de diagnóstico las guarda `svc-contenido`; `svc-ia` no guarda nada |
| Roles | Solo `cliente` y `administrador` | No hay funciones que requieran otro rol; agregar uno después es una migración pequeña |
| Commits y push | Siempre manuales, por cada integrante | Claude Code no ejecuta `git commit` ni `git push` en este proyecto |
