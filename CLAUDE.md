# AgroIA-Web

Plataforma web para el agronegocio del aguacate: tienda de insumos, asistente conversacional AgroIA y diagnóstico de enfermedades por imagen. Proyecto académico (TecNM Jiquilpan), arquitectura de microservicios.

Este archivo resume las reglas que siempre deben respetarse. El detalle está en:

- `docs/definicion-tecnica.md`: servicios, contratos de API, modelo de datos, frontend, entorno local y plan por fases. Consulta los contratos y modelos aquí antes de implementar un endpoint.
- `docs/requerimientos-autenticacion.md`: qué implica cada tarea de autenticación (registro, verificación, JWT, recuperación, roles, límites de intentos, 2FA).

Si algo de este archivo contradice esos documentos, gana este archivo; avisa de la contradicción.

## Stack

- Python 3.12, Django 5.2 LTS, Django REST Framework, drf-spectacular, django-filter.
- Autenticación: djangorestframework-simplejwt (RS256) + django-axes.
- PostgreSQL 16, MongoDB 7 (pymongo), Redis 7 (caché del límite de intentos y eventos con Redis Streams).
- `svc-ia` usa FastAPI (reutiliza el agente del repo BryanGEP/AgroIA).
- Frontend en `web/`: plantillas de Django + Tailwind CSS 4 + daisyUI 5 (vía `django-tailwind-cli`, sin Node) + HTMX 2 (`django-htmx`) + Alpine.js 3.
- Pruebas: pytest, pytest-django, factory-boy, responses, mongomock, fakeredis. Estilo: ruff.
- Todo corre con `docker compose up --build`.

## Servicios

| Servicio | Responsabilidad | Base | Puerto local |
|---|---|---|---|
| `web` | Gateway: plantillas, sesión, enruta, valida JWT | sesiones en PostgreSQL | 8000 |
| `svc-usuarios` | Registro, login, JWT, recuperación, roles, perfil, direcciones | PostgreSQL `usuarios_db` | 8001 |
| `svc-tienda` | Categorías, productos, carrito, pedidos | PostgreSQL `tienda_db` | 8002 |
| `svc-contenido` | Conversaciones, diagnósticos, bitácora | MongoDB `contenido` | 8003 |
| `svc-ia` | Agente y modelo de visión (sano / rona / antracnosis) | ninguna | 8004 |

Dentro de Docker cada servicio escucha en el puerto 8000 y se llama por su nombre (`http://svc-tienda:8000`).

Además corren `agente` (el agente del repo BryanGEP/AgroIA, construido desde GitHub; svc-ia lo llama por HTTP) y `agente-db` (su base de conocimiento, PostgreSQL con pgvector, que solo usa el agente), tres procesos de eventos (misma imagen que su servicio, otro comando): `svc-contenido-eventos` (bitácora y resultados de la IA), `svc-usuarios-eventos` (correos) y `svc-ia-worker` (atiende las solicitudes de IA y llama al agente), más `postgres`, `mongo` y `redis`: trece contenedores.

## Estructura

```text
AgroIA-Web/
├── CLAUDE.md
├── docker-compose.yml
├── .env.example
├── ruff.toml
├── docs/                 # entregables, colección de Postman
├── infra/                # init de PostgreSQL, llaves JWT, tokens de prueba, matriz de accesos
├── comun/agroia_comun/   # autenticación JWT, permisos, formato de errores, eventos
├── web/                  # gateway con plantillas
├── svc-usuarios/
├── svc-tienda/
├── svc-contenido/
└── svc-ia/               # FastAPI
```

Cada servicio Django: `config/` (settings y urls), `apps/<app>/` con `models.py`, `serializers.py`, `views.py`, `filters.py`, `servicios.py`, `urls.py`, `admin.py` y `tests/`. Cada servicio tiene su `Dockerfile`, `requirements.txt`, `requirements-dev.txt` y `README.md`.

## Reglas de arquitectura

- El navegador solo habla con `web`. Ningún servicio interno se expone hacia afuera.
- Cada servicio es dueño de su base. Nunca leas ni escribas la base de otro servicio; usa su API.
- Entre servicios no hay ForeignKey: guarda `usuario_id` como UUID (el `id` de svc-usuarios, compatible con ms-usuarios; en MongoDB, como texto). El contrato de los tokens está en `docs/contrato-identidad.md`.
- Código compartido (autenticación JWT, permisos, formato de errores y eventos) solo en `comun/agroia_comun/`. No lo copies a los servicios.
- Entre servicios: lo que necesita respuesta inmediata va por HTTP síncrono, siempre con timeout; los avisos y lo lento van por eventos con Redis Streams (`agroia_comun.eventos`, catálogo y reglas en `docs/eventos.md`). No acoples la lógica de negocio al transporte.
- Eventos: publica después del commit (`publicar_al_confirmar`) y solo con los campos del catálogo, sin tokens ni datos personales innecesarios; todo manejador de eventos debe ser idempotente por sí mismo; cada consumidor corre en su propio contenedor. Los correos se envían por el evento `correo_solicitado` (consumidor de svc-usuarios), nunca dentro de una petición, y el token del enlace lo genera el consumidor.
- Correlación: cada petición lleva `X-Correlacion-Id` (UUID validado por `CorrelacionMiddleware` de `comun`, en el gateway y en cada servicio); el gateway la reenvía y los eventos la heredan. Los logs del gateway registran la ruta como patrón, nunca la ruta real ni la query string (pueden llevar tokens).
- La IA es asíncrona: el chat y el diagnóstico piden a `svc-contenido` (202), que guarda la solicitud y publica el evento; `svc-ia-worker` responde por evento y la pantalla consulta el estado con polling de HTMX. El gateway no toca Redis. Detalle en `docs/eventos.md` («IA asíncrona»).
- Los endpoints síncronos de `svc-ia` (`/agente/preguntar/`, `/diagnostico/`) quedan por compatibilidad y responden siempre con `id` y `estado`. `svc-ia` no guarda nada: las imágenes y resultados de diagnóstico los guarda `svc-contenido`.
- Nunca presentes un diagnóstico inventado como real: el clasificador de prueba (`IA_CLASIFICADOR_PRUEBA`) solo funciona con `DEBUG=True` y todo lo que da va marcado como prueba.
- `svc-ia` valida el JWT con PyJWT (las clases de DRF de `comun/` no le sirven) e instala solo el núcleo de `comun` (sin Django ni DRF), para los eventos.
- La ficha técnica variable del producto es un `JSONField` en PostgreSQL. MongoDB solo guarda conversaciones, diagnósticos y bitácora.
- Archivos (imágenes de productos y diagnósticos) siempre con `STORAGES` / `default_storage` de Django, nunca rutas a mano: en la Entrega 5 se pasarán a Cloud Storage cambiando solo la configuración.
- El pago es simulado: un botón "Pagar" marca el pedido como `pagado` y la interfaz muestra la etiqueta "pago simulado". No integres pasarelas de pago.
- Roles: solo `cliente` y `administrador`.

## Convenciones de API

- Rutas bajo `/api/v1/`, documentación en `/api/docs/`, salud en `GET /salud/` → `{"estado": "ok"}`. Excepción: `svc-ia` (FastAPI) expone sus rutas sin prefijo (`/agente/preguntar/`, `/diagnostico/`, `/solicitudes/<id>/`), como dice su contrato en la definición técnica; no las cambies.
- Errores: `{"error": "codigo_corto", "detalle": "mensaje para el usuario"}`.
- Listados paginados con `?page=` (20 por página), filtros con django-filter.
- `ViewSet` + router para CRUD; `APIView` solo para acciones que no son CRUD.
- Documenta cada endpoint con `@extend_schema` (descripción y ejemplos).
- No cambies un contrato de API definido en la definición técnica sin avisar al equipo; si es necesario, actualiza también la colección de Postman en `docs/postman/`.

## Convenciones de código

- Identificadores en español, sin acentos ni ñ: `Direccion`, `rona`, `anio`. Lo propio de Django/DRF se queda en inglés.
- Lógica de negocio en `servicios.py` de cada app, no en vistas ni serializers.
- Dinero siempre `Decimal`. Operaciones de stock o dinero dentro de `transaction.atomic()` con `select_for_update()`.
- Los pedidos copian nombre, precio y dirección al momento de comprar.
- Configuración solo por variables de entorno (documentadas en `.env.example`). Nunca escribas secretos, llaves ni contraseñas en el código.
- Nunca subas `.env`, `*.pem` ni `infra/llaves/`.
- `ruff check` y `ruff format` deben pasar.

## Seguridad

- `AUTH_ACTIVA` vale `True` por defecto en el código. Solo el `.env` local puede ponerla en `False`.
- Contraseñas siempre con `create_user` / `set_password`; nunca asignes `password` directo.
- Mensajes genéricos en login y recuperación: no reveles si un correo existe.
- No metas datos sensibles en los claims del JWT (teléfono, dirección).
- No registres contraseñas ni tokens en logs.
- Endpoints protegidos: 401 sin token, 403 con rol equivocado.
- Los 401 y 403 se registran solos en el log `seguridad` (`agroia_comun.seguridad`); los eventos propios usan `registrar_evento`, nunca `print` ni datos sensibles.

## Frontend (`web/`)

- daisyUI para componentes, Tailwind para ajustes de diseño, HTMX para lo que depende del servidor, Alpine para lo que pasa solo en el navegador.
- Dirección visual «Altura» (detalle en `docs/avances/diseno-front.md`): temas `agroia` y `agroia-oscuro` en `static/css/fuente.css`, con los colores propios como utilidades (`bg-bosque`, `text-suave`, `bg-tarjeta`, `text-andosol`, `text-aviso`…). Encabezado, pie y bandas de sección en Bosque con las curvas de nivel (`.curvas`, máscara de `static/img/curvas.svg`); contenido sobre Niebla en tarjetas.
- Contraste AA siempre: Pulpa (`accent`) nunca como texto sobre fondo claro; el texto secundario con `text-suave`, nunca con `opacity-*` ni `text-warning` (no llegan a 4.5:1). Si agregas un par de colores, súmalo a la tabla de contrastes del avance de diseño.
- Componentes del diseño: `encabezado`, `pie`, `seccion` (banda de título), `tarjeta_producto` (la «parcela» 4:3), `estado_vacio`, `error`, `foto_ambiente`. En las listas que se desplazan de lado, `data-desplazar-al-foco`; en las tablas del panel, `tabla-tarjetas` con `data-etiqueta` en cada celda.
- Fotos de ambiente opcionales en `static/img/ambiente/<nombre>.webp` (etiqueta `{% foto_ambiente %}`): sin foto la página se ve igual. Toda imagen con `alt`, `width`, `height` y `loading="lazy"` (salvo la de arriba de la página), desde `static/` o el almacenamiento, nunca de otro dominio. Cada foto se registra en `docs/creditos-imagenes.md`; las de enfermedades, solo reales con licencia libre, nunca generadas por IA.
- Comentarios de plantilla de varias líneas con `{% comment %}`: un `{# #}` partido se ve en la página (hay una prueba que lo revisa).
- Clases que solo pone JavaScript no las genera Tailwind (lee las plantillas): usa un atributo `data-*` con su regla en `fuente.css`.
- Todas las páginas extienden `templates/base.html`.
- Fragmentos de HTMX en `templates/<modulo>/parciales/_nombre.html`; la vista devuelve el parcial si `request.htmx`, si no la página completa.
- Componentes repetidos como `{% include %}` en `templates/componentes/`.
- CSRF para HTMX con `hx-headers` en el `<body>` de `base.html`.
- Indicador de carga (`hx-indicator` + `loading` de daisyUI) en peticiones que tarden, sobre todo agente y diagnóstico.
- Diseño mobile-first. Cada `input` con `label`, cada imagen con `alt`.
- HTMX y Alpine se sirven desde `static/vendor/`, no desde CDN. Alpine es la versión CSP (`@alpinejs/csp`): la lógica compleja va en `Alpine.data()` dentro de `static/js/`; sin `hx-on`, sin scripts ni estilos en línea (`style=`, `onclick=`), porque la Content-Security-Policy no permite `unsafe-inline` ni `unsafe-eval`.
- El proxy `/api/<servicio>/` del gateway solo acepta el token en `Authorization`, nunca el de la sesión.
- Widget flotante de AgroIA (`templates/agroia/parciales/_widget.html`, componente `widgetAgroia`): está en `base.html` salvo en /agroia/, las pantallas de acceso, el panel de administración y las páginas de error (vacían el bloque `widget_agroia`). Comparte con /agroia/ los parciales del chat y el flujo asíncrono; su conversación vive en la sesión del gateway. Carga diferida: cerrado y sin pregunta pendiente no hace peticiones. En celular la burbuja se oculta mientras se baja y vuelve al subir, al detenerse o al recibir el foco (nunca con el panel abierto ni con una respuesta sin leer).
- Cabeceras del gateway: la CSP estricta y `Permissions-Policy` (el micrófono solo para este sitio, para el dictado por voz del widget, detrás de un aviso). En HTMX, `style` no está en `attributesToSettle`: copiarlo violaría la CSP.
- No uses Bootstrap, React ni jQuery.

## Pruebas

- Cada app tiene `tests/` (`test_modelos.py`, `test_endpoints.py`, `test_servicios.py` si aplica).
- Por endpoint: caso correcto, validación que falla y, con `AUTH_ACTIVA=True`, 401 y 403.
- Simula llamadas a otros servicios y al LLM con `responses` o `unittest.mock`; las pruebas no dependen de otros contenedores.
- `svc-contenido` usa `mongomock`; los eventos se prueban con `fakeredis` (Redis simulado).
- Al terminar una tarea, corre las pruebas del servicio: `docker compose exec <servicio> pytest`.

## Comandos

```bash
docker compose up --build
docker compose exec <servicio> pytest
docker compose exec <servicio> ruff check .
docker compose exec <servicio> ruff format .
docker compose exec <servicio> python manage.py makemigrations
docker compose exec web python manage.py tailwind build
docker compose logs -f <servicio>
```

## Git: nunca hagas commit ni push

- Nunca ejecutes `git commit`, `git push`, `git merge`, `git rebase`, `git reset` ni ningún comando que cambie el historial o el remoto. Los commits y push los hace cada integrante a mano.
- Puedes usar comandos de solo lectura (`git status`, `git diff`, `git log`) para entender el estado.
- Al terminar una tarea, sugiere el mensaje de commit con el formato del proyecto, pero no lo ejecutes.

## Flujo de trabajo

- Ramas desde `develop` (`feat/`, `fix/`, `docs/`, `test/`, `refactor/`); PR hacia `develop`, nunca hacia `main`. Ver `CONTRIBUTING.md`.
- Commits con formato `tipo(área): descripción`, por ejemplo `feat(tienda): filtros de productos`.
- Antes de implementar algo no trivial, propone un plan y espera aprobación.
- Escribe primero las pruebas de la lógica de negocio y los endpoints.
- No agregues dependencias nuevas sin mencionarlo; si las agregas, fíjalas en el `requirements.txt` del servicio.
- No hagas cambios fuera del servicio de la tarea salvo que sean necesarios, y dilo explícitamente.
- Al terminar una tarea, sugiere el mensaje de commit con el formato del proyecto, pero no lo ejecutes. El mensaje nunca debe incluir `Co-Authored-By` ni ninguna mención a Claude o Claude Code.

## Documentación de avances

- Al terminar una fase o un avance grande, crea o actualiza `docs/avances/<fase>.md` con la misma estructura que `docs/avances/fase-0-base-monorepo.md` y agrega su fila al índice `docs/avances/README.md`.
- Al terminar cada sesión de trabajo, propón la entrada del día para `docs/bitacora.md` con el formato definido ahí, y pregunta el nombre del integrante (y el sprint) si no lo sabes.
- No inventes resultados: solo documenta lo que se verificó.
