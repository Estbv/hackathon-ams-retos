# orders-api: ficha del servicio y referencia de la API

## 1. Qué es

`orders-api` es la API de pedidos de la tienda online. Atiende tres operaciones:

| Endpoint | Función | % del tráfico | Criticidad |
|---|---|---|---|
| `GET /api/products/{id}` | Catálogo de productos | 60% | Media |
| `GET /api/orders/{id}` | Consulta de pedidos | 25% | Alta |
| `POST /api/checkout` | Pago y creación del pedido | 15% | **Crítica** (es la que genera ingresos) |

**Tráfico normal:** unas 600 peticiones por minuto.

**Dependencias:**

```
                 ┌──────────────► orders-db (PostgreSQL 15, pool de 20 conexiones)
 clientes ──► orders-api ──────► orders-cache (Redis)
 (Java 21,       │
  Spring Boot)   └──────────────► api.payprovider.example (proveedor de pagos, HTTPS)
                 disco local: /var/log/orders (logs y recibos)
```

## 2. Valores normales

| Métrica | Valor normal |
|---|---|
| `error_rate` | 0,1% a 0,3% |
| `latency_p50_ms` | unos 80 ms |
| `latency_p95_ms` | unos 180 ms |
| `cpu_pct` | 20% a 30% |
| `memory_mb` | unos 520 MB de 1.024 MB |
| `disk_used_pct` | unos 54% |
| `db_pool_active` | 3 a 6 de 20, con `db_pool_waiting` = 0 |
| `cache_hit_rate` | unos 0,93 |

## 3. Objetivos de nivel de servicio (SLO)

| SLO | Objetivo |
|---|---|
| Disponibilidad (peticiones sin error 5xx) | ≥ 99,5% |
| Latencia p95 | < 800 ms |
| Tasa de error de `POST /api/checkout` | < 1% |

## 4. Matriz de severidad

| Severidad | Criterio | Respuesta esperada |
|---|---|---|
| **SEV1** | Servicio caído, o checkout fallando para la mayoría de los clientes | Aviso inmediato a guardia y a la gerencia |
| **SEV2** | Una función crítica muy degradada (checkout con errores > 5%), o un SLO muy incumplido | Aviso inmediato a guardia |
| **SEV3** | Degradación sin errores relevantes (por ejemplo, latencia fuera del SLO), o un riesgo inminente (disco > 85% y creciendo) | Ticket para el horario laboral, con seguimiento |
| **SEV4** | Informativo: anomalía sin impacto en clientes | Registro, sin aviso |

## 5. API de observabilidad del simulador

Base: `http://<host>:8080`. Todas las respuestas son JSON.

### El servicio

| Método y ruta | Devuelve |
|---|---|
| `GET /health` | `{"status": "UP"}` o 503 `{"status": "DOWN"}`. **Ojo:** solo indica que el proceso responde. |
| `GET /health/deep` | El estado de cada dependencia y del disco. Devuelve 503 si alguna no está UP. |
| `GET /api/products/{id}`, `GET /api/orders/{id}`, `POST /api/checkout` | Peticiones reales al servicio. Sirven para pruebas sintéticas. Responden con la latencia y los errores del momento. |

### Métricas

| Método y ruta | Devuelve |
|---|---|
| `GET /metrics` | La foto actual: `up`, `version`, `requests_per_min`, `error_rate`, `errors_by_endpoint`, `latency_p50_ms`, `latency_p95_ms`, `cpu_pct`, `memory_mb`, `memory_limit_mb`, `disk_used_pct`, `db_pool_active`, `db_pool_max`, `db_pool_waiting`, `cache_hit_rate`, `restarts_total`. Con el servicio caído: `up: 0`. |
| `GET /metrics/history?minutes=30` | Una foto cada 10 s, hasta 360 minutos. |

### Logs

`GET /logs` devuelve los logs de la aplicación (`source=app`) y de acceso (`source=access`).

| Parámetro | Uso |
|---|---|
| `level` | Nivel mínimo: DEBUG, INFO, WARN o ERROR |
| `source` | `app` o `access` |
| `since`, `until` | Fecha y hora ISO 8601 |
| `q` | Texto a buscar |
| `limit` | Por defecto 200, máximo 2.000. Devuelve las más recientes. |

Respuesta: `{"count", "truncated", "lines": [...]}`.

**Los logs contienen datos sensibles** (contraseñas, tokens, tarjetas, correos e IP de clientes). Protéjanlos antes de enviarlos al modelo.

### Contexto operativo

| Método y ruta | Devuelve |
|---|---|
| `GET /dependencies` | El estado de cada dependencia según un chequeo `tcp-ping` |
| `GET /changes?since=...` | Despliegues y cambios de configuración e infraestructura |
| `GET /calendar` | Jobs y ventanas programadas |

### Gestión de incidentes (ITSM)

| Método y ruta | Uso |
|---|---|
| `POST /itsm/incidents` | Crea un incidente. Campos obligatorios: `title`, `severity` (SEV1 a SEV4) y `summary`. El resto de los campos son libres y se guardan tal cual. Devuelve el incidente con su `id` (INC-SIM-0001…). |
| `GET /itsm/incidents`, `GET /itsm/incidents/{id}` | Consulta de incidentes |
| `POST /itsm/incidents/{id}/update` | Actualiza el incidente: `{"status": "OPEN" \| "MITIGATED" \| "RESOLVED", "severity": "...", "note": "...", ...}` |

Los parámetros inválidos (por ejemplo, un `level` o una fecha mal escrita) devuelven 400 con un `detail` que explica el problema. Cómo conectarse correctamente: [`guia-conexion.md`](guia-conexion.md).

Esta es toda la API. No hay otros endpoints: cualquier otra ruta responde 404. Los escenarios de falla se eligen al arrancar el simulador (ver `simulador/README.md`).
