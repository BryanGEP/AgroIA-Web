# AgroIA-Web

Plataforma web para el agronegocio del aguacate: tienda en línea de insumos, asistente conversacional AgroIA y diagnóstico de enfermedades por imagen.

Proyecto académico (Ingeniería en Sistemas Computacionales — TecNM Jiquilpan). Metodología Scrum, gestión en Jira. Repositorio monorepo con arquitectura de microservicios sobre Django.

## Estructura

| Carpeta | Descripción | Instalación |
| :-- | :-- | :-- |
| `web/` | Frontend y gateway en Django: vistas, templates, sesión y widget de AgroIA. | Próximamente |
| `svc-usuarios/` | Registro, login (JWT), recuperación de contraseña, roles y direcciones. PostgreSQL. | Próximamente |
| `svc-catalogo/` | Productos, categorías, stock, búsqueda y filtros. MongoDB. | Próximamente |
| `svc-pedidos/` | Carrito, pedidos, método de pago y estado. PostgreSQL y MongoDB. | Próximamente |
| `svc-agente/` | Chat con AgroIA e historial de conversaciones. Se integrará desde el repositorio [AgroIA](https://github.com/BryanGEP/AgroIA). | Próximamente |
| `svc-diagnostico/` | Clasificación de imágenes: sano, roña o antracnosis. MongoDB. | Próximamente |
| `docs/` | Documentación del proyecto (sprints, entregables). | [Entregable 1](docs/Entregable1_AgroIAWeb.docx) |

## Entregas

- **Entrega 1:** fundamentos y planeación del proyecto (equipo y roles Scrum, definición del proyecto, arquitectura, configuración de Jira y estándares de trabajo).
  - [Documento del Entregable 1](docs/Entregable1_AgroIAWeb.docx)

## Cómo contribuir

El equipo trabaja con ramas por tarea que se integran en `develop` mediante Pull Requests; `main` está protegida y solo contiene versiones estables.

Antes de hacer cualquier cambio, lee la [guía de contribución](CONTRIBUTING.md). Al abrir un Pull Request se carga automáticamente la [plantilla de PR](.github/pull_request_template.md).

## Equipo

- Isis Lizbeth Vázquez Avalos
- Danna Geraldine Ávila García
- Bryan Gael Esquivel Pérez
