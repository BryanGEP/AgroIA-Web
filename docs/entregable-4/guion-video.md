# Guion del video de la Entrega 4

**Duración:** de 3 a 5 minutos. **Tema:** el flujo asíncrono de AgroIA con Redis Streams: una pregunta que se publica como evento, la procesa svc-ia como worker y la respuesta se guarda en MongoDB. Incluye un fallo con reintento y el registro de los eventos.

## Antes de grabar

1. **Levantar todo** y dejar los datos limpios:

   ```powershell
   docker compose up -d
   docker compose exec svc-usuarios python manage.py reiniciar_limites
   docker compose exec svc-contenido python manage.py reiniciar_limites
   ```

2. **Revisar que Groq responda** con una pregunta de prueba en el widget. Si responde «AgroIA no está disponible» por la cuota, grabar otro día.
3. **Pantalla dividida:**
   - a la izquierda, el navegador en http://localhost:8000 con la sesión de `cliente@demo.agroia.test`, a 1280 × 800 y con un zoom de 110 % para que se lea;
   - a la derecha, una terminal de PowerShell con letra grande.
4. **Dejar en la terminal los logs en vivo**, filtrados a los eventos (así no salen las peticiones de salud ni el correo de consola):

   ```powershell
   docker compose logs -f --no-log-prefix web svc-contenido svc-ia-worker svc-contenido-eventos |
     Select-String '"evento_publicado"|"evento_procesado"|"evento_reintentado"|"evento_fallido"|preguntar'
   ```

5. **Tener a la mano una segunda terminal** para detener y arrancar el agente.
6. **No mostrar** el archivo `.env`, la llave de Groq ni la terminal de `svc-usuarios-eventos` (imprime los correos de prueba con sus enlaces).

## Escenas

| Tiempo | Qué se ve | Qué se dice |
| --- | --- | --- |
| 0:00 – 0:25 | Diagrama del flujo de eventos ([`docs/eventos.md`](../eventos.md), «Diagrama del flujo de eventos») | «AgroIA-Web son cinco microservicios. En esta entrega, lo que tarda o lo que solo es un aviso deja de ser una llamada directa: se publica como evento en Redis Streams y otro servicio lo consume a su ritmo. El caso principal es la pregunta a la inteligencia artificial.» |
| 0:25 – 0:45 | El inicio del sitio; se abre la burbuja de AgroIA | «El usuario abre el chat en cualquier página. Al enviar la pregunta, el navegador no espera al modelo.» |
| 0:45 – 1:20 | Se escribe una pregunta corta («¿Cada cuánto riego un aguacate joven?») y se envía. Aparece «AgroIA está escribiendo…». En la terminal salen las líneas | «El gateway manda la pregunta a svc-contenido, que la guarda y responde 202 al instante. En la terminal se ve `evento_publicado` con el tipo `ia_pregunta_solicitada`: la solicitud ya está en Redis. Todas las líneas llevan el mismo `correlacion_id`, que puso el gateway.» |
| 1:20 – 1:50 | Llega la respuesta con sus fuentes. En la terminal: `evento_procesado` del worker, `evento_publicado` de `ia_respuesta_generada` y `evento_procesado` de svc-contenido-eventos | «svc-ia trabaja como worker: tomó la solicitud del stream, llamó al agente y publicó el resultado. svc-contenido lo guardó en MongoDB, y la página lo mostró al consultar el estado cada dos segundos con HTMX. La pregunta y la respuesta nunca aparecen en los logs: solo ids y tiempos.» |
| 1:50 – 2:10 | Segunda terminal: `docker compose stop agente` | «Ahora vamos a apagar el agente para ver qué pasa cuando la inteligencia artificial no responde.» |
| 2:10 – 2:50 | Otra pregunta en el widget. En la terminal salen `evento_reintentado` (dos veces) y después `evento_fallido`. En el widget aparece el aviso con «Reintentar» | «El worker reintenta dos veces, con espera creciente, porque el error es temporal. Al agotar los reintentos, publica `ia_respuesta_fallida` y el evento queda en el stream de fallidos. El usuario no se queda esperando: ve el aviso y un botón para reintentar. Su pregunta quedó guardada.» |
| 2:50 – 3:20 | `docker compose start agente`; esperar a que esté *healthy* (`docker compose ps agente`). Clic en «Reintentar»; llega la respuesta | «Con el agente de vuelta, Reintentar crea otra solicitud para la misma pregunta, sin repetirla, y ahora sí llega la respuesta.» |
| 3:20 – 3:50 | Cerrar sesión y entrar con `admin@demo.agroia.test`. Panel → **Eventos**. Señalar los streams, los grupos, los pendientes en 0 y la tabla de fallidos | «El administrador ve el estado de Redis sin entrar a Redis: cada stream, sus grupos de consumidores y los fallidos. El motivo sale solo con el nombre de la excepción y sin los datos del evento. Reprocesar o descartar se hace con un comando, que la pantalla indica.» |
| 3:50 – 4:20 | Terminal: `docker compose exec svc-contenido python -m agroia_comun.eventos estado` y después `descartar --id <id>` del fallido de la prueba | «Es el mismo estado desde la terminal. Revisamos el fallido: es la pregunta del agente apagado, que ya se respondió con Reintentar. Como guardó la pregunta sin sus datos, no se puede reprocesar, así que se descarta.» |
| 4:20 – 4:50 | Panel → **Pedidos** → un pedido pagado → «Línea de tiempo» → «ver el flujo completo» (la bitácora filtrada por la correlación) | «Los eventos de negocio, como crear o pagar un pedido, quedan en la bitácora de svc-contenido. Con la correlación vemos todo lo que disparó una sola acción del usuario, de punta a punta.» |
| 4:50 – 5:00 | Volver al diagrama | «Así, los servicios se avisan por eventos sin esperarse, la IA es asíncrona y lo que falla queda registrado para revisarlo. Gracias.» |

## Al terminar

- Descartar los fallidos de la grabación después de revisarlos con `estado`.
- Correr `limpiar_datos_prueba` si se creó algún usuario o pedido.
- Subir el video y pegar el enlace en [`docs/entregable-4.md`](../entregable-4.md#video).

**Video de apoyo sin narración:** hay un video corto, grabado con Playwright, del flujo principal: la pregunta en el widget, la espera y la respuesta, y en el panel el estado de los eventos y la bitácora. Sirve de referencia para el ritmo y lo que hay que mostrar.
