# Kit del reto

| Archivo | Contenido |
|---|---|
| `datos/checkout-incident/*.log` | Logs del incidente: aplicación (Spring Boot), monitor de Oracle, acceso y errores de Nginx. 1.780 líneas en total. |
| `datos/checkout-incident/ticket.json` | Ticket del incidente tal como lo recibe el equipo AMS. |
| `datos/problemas_conocidos.json` | Base de problemas conocidos del equipo (KI-001 a KI-006). |
| `maas_ejemplo.py` | Llamada mínima a GLM en Huawei Cloud MaaS desde Python. |

Los logs contienen datos sensibles ficticios a propósito (contraseñas, tarjetas, correos, tokens, IP). Su solución debe protegerlos antes de enviarlos al modelo.
