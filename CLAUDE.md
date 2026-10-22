# AgroIA-Web

Plataforma web para el agronegocio del aguacate: tienda de insumos, asistente conversacional AgroIA y diagnóstico de enfermedades por imagen. Proyecto académico (TecNM Jiquilpan), arquitectura de microservicios.

Este archivo resume las reglas que siempre deben respetarse. El detalle está en:

- `docs/definicion-tecnica.md`: servicios, contratos de API, modelo de datos, frontend, entorno local y plan por fases. Consulta los contratos y modelos aquí antes de implementar un endpoint.
- `docs/requerimientos-autenticacion.md`: qué implica cada tarea de autenticación (registro, verificación, JWT, recuperación, roles, límites de intentos, 2FA).

Si algo de este archivo contradice esos documentos, gana este archivo; avisa de la contradicción.

## Stack

- Python 3.12, Django 5.2 LTS, Django REST Framework, drf-spectacular, django-filter.
- Autenticación: djangorestframework-simplejwt (RS256) + django-axes.
- PostgreSQL 16, MongoDB 7 (pymongo), Redis 7.
- `svc-ia` usa FastAPI (reutiliza el agente del repo BryanGEP/AgroIA).
- Frontend en `web/`: plantillas de Django + Tailwind CSS 4 + daisyUI 5 (vía `django-tailwind-cli`, sin Node) + HTMX 2 (`django-htmx`) + Alpine.js 3.
- Pruebas: pytest, pytest-django, factory-boy, responses, mongomock. Estilo: ruff.
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

## Estructura

```text
AgroIA-Web/
├── CLAUDE.md
├── docker-compose.yml
├── .env.example
├── ruff.toml
├── docs/                 # entregables, colección de Postman
├── infra/                # init de PostgreSQL, script de llaves JWT
├── comun/agroia_comun/   # autenticación JWT, permisos, formato de errores
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
- Entre servicios no hay ForeignKey: guarda `usuario_id` como entero.
- Código compartido (autenticación JWT, permisos, formato de errores) solo en `comun/agroia_comun/`. No lo copies a los servicios.
- Llamadas entre servicios: HTTP síncrono por ahora, siempre con timeout. En la Entrega 4 se pasarán a eventos por Redis; no acoples la lógica al transporte.
- `svc-ia` responde siempre con `id` y `estado`, aunque hoy siempre sea `"listo"`. No guarda nada: las imágenes y resultados de diagnóstico los guarda `svc-contenido`.
- `svc-ia` valida el JWT con PyJWT (las clases de `comun/` son de DRF).
- La ficha técnica variable del producto es un `JSONField` en PostgreSQL. MongoDB solo guarda conversaciones, diagnósticos y bitácora.
- Archivos (imágenes de productos y diagnósticos) siempre con `STORAGES` / `default_storage` de Django, nunca rutas a mano: en la Entrega 5 se pasarán a Cloud Storage cambiando solo la configuración.
- El pago es simulado: un botón "Pagar" marca el pedido como `pagado` y la interfaz muestra la etiqueta "pago simulado". No integres pasarelas de pago.
- Roles: solo `cliente` y `administrador`.

## Convenciones de API

- Rutas bajo `/api/v1/`, documentación en `/api/docs/`, salud en `GET /salud/` → `{"estado": "ok"}`.
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

## Frontend (`web/`)

- daisyUI para componentes, Tailwind para ajustes de diseño, HTMX para lo que depende del servidor, Alpine para lo que pasa solo en el navegador.
- Tema propio `agroia` (primario verde aguacate) en `static/css/fuente.css`.
- Todas las páginas extienden `templates/base.html`.
- Fragmentos de HTMX en `templates/<modulo>/parciales/_nombre.html`; la vista devuelve el parcial si `request.htmx`, si no la página completa.
- Componentes repetidos como `{% include %}` en `templates/componentes/`.
- CSRF para HTMX con `hx-headers` en el `<body>` de `base.html`.
- Indicador de carga (`hx-indicator` + `loading` de daisyUI) en peticiones que tarden, sobre todo agente y diagnóstico.
- Diseño mobile-first. Cada `input` con `label`, cada imagen con `alt`.
- HTMX y Alpine se sirven desde `static/vendor/`, no desde CDN.
- No uses Bootstrap, React ni jQuery.

## Pruebas

- Cada app tiene `tests/` (`test_modelos.py`, `test_endpoints.py`, `test_servicios.py` si aplica).
- Por endpoint: caso correcto, validación que falla y, con `AUTH_ACTIVA=True`, 401 y 403.
- Simula llamadas a otros servicios y al LLM con `responses` o `unittest.mock`; las pruebas no dependen de otros contenedores.
- `svc-contenido` usa `mongomock`.
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
