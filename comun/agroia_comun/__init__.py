"""Paquete compartido de AgroIA-Web.

- Núcleo, sin Django (lo instalan todos, también svc-ia): `tokens` (validar el access con
  PyJWT) y `eventos` (Redis Streams).
- Con el extra [django] (web, svc-usuarios, svc-tienda y svc-contenido): autenticación y
  permisos de DRF, formato de errores, log de seguridad y configuración.
"""
