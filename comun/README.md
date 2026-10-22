# comun — paquete compartido `agroia_comun`

Código que comparten los servicios Django (`web`, `svc-usuarios`, `svc-tienda` y `svc-contenido`). `svc-ia` no lo instala: valida el JWT con PyJWT.

| Módulo | Contenido | Fase |
| --- | --- | --- |
| `autenticacion.py` | Validación del JWT RS256 con la llave pública, controlada por `AUTH_ACTIVA` | 4 |
| `permisos.py` | Permisos por rol (`cliente`, `administrador`) | 4 |
| `errores.py` | Formato `{"error": "...", "detalle": "..."}` | 1 |

## Cómo se instala

- **Docker:** cada `Dockerfile` copia `comun/` a `/comun` y lo instala con `pip install -e /comun`. `docker-compose.yml` monta `./comun` en `/comun`, así que los cambios se ven sin reconstruir la imagen.
- **Venv local de la raíz:** el `requirements-dev.txt` de la raíz lo instala en modo editable (`-e ./comun`).

No copies este código dentro de los servicios: impórtalo desde `agroia_comun`.
