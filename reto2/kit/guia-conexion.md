# Guía de conexión con el servicio a monitorear

Esta guía explica cómo debe conectarse su sistema de agentes con `orders-api`, y cómo comprobar que la conexión es correcta **antes** de construir encima de ella. La referencia completa de cada endpoint está en [`servicio.md`](servicio.md).

---

## 1. Cómo se conecta

Su sistema es un **cliente HTTP** del simulador. El simulador hace de servicio en producción, de plataforma de observabilidad y de sistema de tickets. No hay que instalar nada en el simulador, ni ejecutar agentes dentro de él.

```
 ┌──────────────── su sistema ─────────────────┐                ┌───── simulador ──────┐
 │                                              │                │                      │
 │  Monitor (bucle, código) ──┐                 │   HTTP / JSON  │  /health, /metrics   │
 │                            ├──► Conector ────┼──────────────► │  /logs, /changes ... │
 │  Agentes (GLM) ──tools─────┘    · timeouts   │                │                      │
 │                                 · reintentos │  POST          │  /itsm/incidents     │
 │                                 · enmascarado├──────────────► │  (único lugar donde  │
 │                                 · límite de  │                │   se escribe)        │
 │                                   carga      │                └──────────────────────┘
 └──────────────────────┬───────────────────────┘
                        │ HTTPS
                        ▼
             Huawei Cloud MaaS (GLM)
```

**Regla de diseño:** toda comunicación con el servicio pasa por **un único conector**. El monitor y los agentes nunca hacen peticiones HTTP por su cuenta. Así, los timeouts, el enmascarado y el límite de carga se aplican en un solo lugar.

---

## 2. Configuración

Toda la conexión se configura con variables de entorno. **Entre la práctica y la evaluación solo cambia `SIM_BASE_URL`.**

| Variable | Práctica | Evaluación |
|---|---|---|
| `SIM_BASE_URL` | `http://localhost:8080` | La URL que entrega el jurado, por ejemplo `http://10.0.5.20:8081` |
| `MAAS_ENDPOINT` | `https://api-ap-southeast-1.modelarts-maas.com/v2/chat/completions` | Igual |
| `MAAS_MODEL` | `glm-5.2` | Igual |
| `MAAS_API_KEY` | La clave de su equipo | Igual. Nunca en el repositorio. |

Archivo `.env.example` sugerido:

```bash
SIM_BASE_URL=http://localhost:8080
MAAS_ENDPOINT=https://api-ap-southeast-1.modelarts-maas.com/v2/chat/completions
MAAS_MODEL=glm-5.2
MAAS_API_KEY=
```

---

## 3. Verificar la conexión (obligatorio antes de empezar)

El kit incluye `verificar_conexion.py`. Comprueba cada endpoint, el formato de las respuestas, el reloj, los errores controlados y, opcionalmente, MaaS. Ejecútenlo **desde la misma máquina y red donde correrá su sistema**:

```bash
# 1. Arranque el simulador (en otra terminal)
cd simulador && python simulador.py

# 2. Verifique la conexión
python verificar_conexion.py --url http://localhost:8080 --maas --probar-itsm
```

**Resultado esperado** con el simulador recién arrancado:

```
[1] Alcance de red: http://localhost:8080
  ✔ Conexión establecida: 3 ms
[2] Servicio
  ✔ GET /health: 200 UP
  ✔ GET /health/deep: 200 UP (database=UP, cache=UP, payment_provider=UP, diskSpace=UP)
[3] Métricas
  ✔ GET /metrics: versión 3.1.4, error_rate=0.0015, p95=164 ms
  ✔ Reloj: diferencia con el servicio +0.5 s
  ! GET /metrics/history: 1 puntos cada 10 s (poco histórico: ...)
[4] Logs
  ✔ GET /logs: 15 líneas disponibles, 15 devueltas
  ! Datos sensibles: los logs llegan SIN enmascarar (es lo esperado): ...
  ✔ Logs incrementales (since con zona horaria, codificado): 200
  ...
[8] Huawei Cloud MaaS
  ✔ Llamada al modelo: respondió en 2.1 s
  ✔ Function calling (tools): el modelo pidió la tool get_metrics

Resultado: 18 OK · 2 advertencias · 0 fallas
```

**Cómo leer el resultado:**

| Resultado | Significado | Qué hacer |
|---|---|---|
| `0 fallas` | La conexión funciona | Pueden construir su sistema |
| ✘ `No se puede conectar con el servicio` | Su máquina no llega al simulador | Revisen la URL, el puerto, el firewall, y que el simulador esté en marcha. No usen `localhost` si el simulador está en otra máquina. |
| ✘ `MAAS_API_KEY ... 401` | La clave no es válida | Revisen la clave que entregó la organización |
| ! `poco histórico` | El simulador arrancó hace poco | Normal. Su sistema debe tolerarlo. |
| ! `logs SIN enmascarar` | Los logs contienen datos sensibles a propósito | Su conector debe enmascararlos |
| ! `GET /health: 503 DOWN` | El servicio está caído **en este momento** | La conexión funciona. Probablemente hay un escenario activo. |
| ! `Reloj ... difieren` | El reloj de su máquina y el del servicio no coinciden | Usen como referencia de tiempo el `timestamp` de `/metrics` (ver sección 6) |
| ! `Function calling ... no acepta 'tools'` | El endpoint o el modelo no admite tools | Pasen el contexto en el mensaje, o consulten a la organización |

El script devuelve el código de salida 0 si todo está bien, 1 si hay advertencias y 2 si hay fallas. Pueden usarlo en sus propias pruebas automáticas.

> **No usen `--probar-itsm` contra el simulador del jurado.** Crea un ticket de prueba, que quedaría registrado en su evaluación. En el simulador del jurado, ejecuten el script **sin** esa opción.

---

## 4. Contrato de los endpoints

Todas las respuestas son JSON en UTF-8. Ejemplos reales del simulador sano:

**`GET /metrics`**

```json
{
  "timestamp": "2026-10-20T14:05:10+00:00",
  "up": 1, "service": "orders-api", "version": "3.1.4",
  "requests_per_min": 616, "error_rate": 0.0015,
  "errors_by_endpoint": {"products": 0.001, "orders": 0.002, "checkout": 0.003},
  "latency_p50_ms": 81, "latency_p95_ms": 192,
  "cpu_pct": 25.8, "memory_mb": 527, "memory_limit_mb": 1024, "disk_used_pct": 54.0,
  "db_pool_active": 4, "db_pool_max": 20, "db_pool_waiting": 0,
  "cache_hit_rate": 0.932, "restarts_total": 0
}
```

Con el servicio caído, la respuesta solo trae `timestamp`, `up: 0`, `service`, `version` y `restarts_total`. **Su código no debe asumir que los demás campos existen.**

**`GET /metrics/history?minutes=30`:** `{"interval_s": 10, "points": [ <mismo formato que /metrics>, ... ]}`. El máximo es de 360 minutos.

**`GET /logs?level=WARN&since=...&limit=200`**

```json
{"count": 32, "truncated": true, "lines": [
  "2026-10-20 14:05:09.553  WARN 4321 --- [http-nio-8080-exec-7] c.o.orders.cache.RedisCacheClient : Redis connection refused ...",
  "198.51.100.208 - - [20/Oct/2026:14:05:10 +0000] \"GET /api/orders/ORD-994781 HTTP/1.1\" 200 1631 \"-\" \"Mozilla/5.0\" rt=0.083"
]}
```

- Hay dos formatos: el de la aplicación (`source=app`) y el de acceso, estilo Nginx (`source=access`).
- `lines` trae las **más recientes**, hasta `limit`.
- Si `truncated` es `true`, hay más líneas de las que se devolvieron: acoten con `since`, `level`, `q` o `source`.

**`GET /health/deep`**

```json
{"status": "UP", "components": {"database": {"status": "UP"}, "cache": {"status": "UP"},
 "payment_provider": {"status": "UP"}, "diskSpace": {"status": "UP", "used_pct": 54.0}}}
```

**`GET /dependencies`:** `{"database": {"status": "UP", "checked_at": "...", "check": "tcp-ping"}, ...}`

**`GET /changes`:** `{"changes": [{"id": "CHG-60871", "time": "...", "type": "deploy", "service": "orders-api", "description": "...", "by": "..."}]}`

**`GET /calendar`:** `{"scheduled": [{"name": "...", "schedule" o "start"/"end": "...", "owner": "...", "expected_impact": "..."}]}`

### Códigos HTTP

| Código | Dónde | Significado para su sistema |
|---|---|---|
| 200 / 201 | Todos | Correcto |
| **503** | `/health`, `/health/deep`, `/api/*` | **El servicio está caído o degradado.** Es información, no un error de conexión. |
| 500 / 502 | `/api/*` | El servicio falla en esa petición. Es información. |
| 400 | `/logs`, `/metrics/history`, `/itsm` | Parámetro inválido. El cuerpo `detail` dice cuál. Es un error de **su** código. |
| 404 | Cualquiera | Ruta inexistente o incidente no encontrado |
| Sin respuesta (timeout, conexión rechazada) | Cualquiera | **No pueden ver el servicio.** No es lo mismo que "el servicio está caído" (ver sección 7). |

---

## 5. Plan de consultas y límite de carga

El límite del reto es de **2 peticiones por segundo en promedio**, incluidas las de los agentes. Plan recomendado para el monitor:

| Endpoint | Cada | Peticiones por segundo |
|---|---|---|
| `GET /metrics` | 10 s | 0,10 |
| `GET /health` | 10 s | 0,10 |
| `GET /health/deep` | 30 s | 0,03 |
| `GET /logs?level=WARN&since=...` | 15 s | 0,07 |
| `GET /changes`, `GET /calendar` | 60 s | 0,03 |
| `POST /api/checkout` (prueba sintética, opcional) | 30 s | 0,03 |
| **Total del monitor** | | **unas 0,4** |

Eso deja unas 1,6 peticiones por segundo para las investigaciones de los agentes.

**Recomendaciones:**
- **Pongan un limitador de peticiones en el conector,** por ejemplo un token bucket a 1,5 peticiones por segundo. Así un agente que llama tools en bucle no puede pasarse del límite.
- **No consulten más seguido de lo que cambian los datos:** las métricas se actualizan cada pocos segundos, y el histórico cada 10 s.
- **Línea base al arrancar:** `GET /metrics/history?minutes=60` en una sola petición, en lugar de esperar una hora acumulando datos.

---

## 6. Tiempo y logs incrementales

En la evaluación, el simulador corre en **otra máquina**, cuyo reloj puede no coincidir con el suyo.

- **La hora de referencia es la del servicio:** el `timestamp` de `/metrics` (ISO 8601, con zona horaria). No usen la hora local de su máquina para pedir logs.
- **Cursor de logs:** guarden el `timestamp` de la última consulta a `/metrics` y úsenlo como `since` en la siguiente consulta a `/logs`.
- **`since` incluye el instante indicado:** pueden recibir otra vez líneas de la consulta anterior. Elimínenlas comparando el texto de la línea.
- **Codifiquen los parámetros en la URL.** El `+` de la zona horaria debe enviarse como `%2B`. Con `requests`, usen `params={...}`, que lo hace solo. Con `urllib`, usen `urllib.parse.urlencode`.
- **Las líneas de log no traen la zona horaria** en el formato de la aplicación. Si las interpretan, asuman la zona del `timestamp` de `/metrics`.

```python
r = session.get(f"{BASE}/logs", params={"since": cursor, "level": "WARN", "limit": 500}, timeout=10)
```

---

## 7. "El servicio está caído" o "no puedo ver el servicio"

Su sistema debe distinguir estas dos situaciones. El reto lo evalúa.

| Lo que ve el conector | Interpretación | Qué hacer |
|---|---|---|
| `/health` responde 503, o `/metrics` trae `up: 0` | **El servicio está caído** | Es una alerta del servicio |
| `/health` responde 200, pero `/api/checkout` falla o `/metrics` muestra errores | **El servicio está degradado** con el health check en UP | Es una alerta del servicio |
| Timeout, conexión rechazada o error de DNS en **todas** las rutas | **No pueden ver el servicio** (falla de red, o el simulador detenido) | **No** abrir un incidente de caída del servicio. Registrar "pérdida de visibilidad", reintentar con espera progresiva y, si persiste, avisar indicando que es un problema de monitoreo. |
| Timeout en una sola ruta, por ejemplo `/api/checkout` lento | Puede ser síntoma del servicio | Comparar con `/metrics` |

**Timeouts recomendados:**
- de 5 a 10 s para las rutas de observabilidad
- unos 10 s para `/api/*`, porque durante una falla puede tardar
- de 120 a 300 s para MaaS: una investigación puede tardar varios minutos

---

## 8. Escribir en el ITSM

Es el **único** lugar donde su sistema escribe.

```python
ticket = {
  "title": "...", "severity": "SEV2", "summary": "...",       # obligatorios
  "impact": "...", "root_cause": "...", "confidence": "Medium",
  "evidence": [...], "recommended_actions": [...], "business_message": "...",
  "detected_at": "...", "anomaly_start_estimate": "...", "source": "agente-<equipo>"
}
r = session.post(f"{BASE}/itsm/incidents", json=ticket, timeout=10)   # 201 → r.json()["id"] = "INC-SIM-0001"
session.post(f"{BASE}/itsm/incidents/INC-SIM-0001/update",
             json={"status": "RESOLVED", "note": "..."}, timeout=10)   # 200
```

- **`severity`:** solo `SEV1`, `SEV2`, `SEV3` o `SEV4`. **`status`:** solo `OPEN`, `MITIGATED` o `RESOLVED`. Otros valores devuelven 400 con los valores permitidos.
- **Guarden el `id` que devuelve el ITSM** en el estado de su sistema. Lo necesitan para actualizar el incidente y para no duplicarlo si su proceso se reinicia.
- **Si el POST falla por timeout,** consulten `GET /itsm/incidents` antes de reintentar. Puede que el incidente sí se haya creado.
- **Nada sensible en los tickets:** todo lo que envíen debe salir de datos ya enmascarados.

---

## 9. Conectar los agentes: tools

Los agentes no llaman a la API directamente: usan **las funciones del conector como tools**. Hay dos formas.

**A. Function calling de GLM.** Se envía la lista de tools en el parámetro `tools` de la llamada a MaaS, con el formato compatible con OpenAI. Cuando el modelo pide una tool, su código ejecuta la función del conector y le devuelve el resultado en un mensaje con `"role": "tool"`.

```json
{"type": "function", "function": {
  "name": "buscar_logs",
  "description": "Busca logs de orders-api ya enmascarados.",
  "parameters": {"type": "object", "properties": {
    "q": {"type": "string"}, "level": {"type": "string", "enum": ["INFO", "WARN", "ERROR"]},
    "since": {"type": "string", "description": "ISO 8601"}}, "required": []}}}
```

**B. Servidor MCP** (bonus): exponen el conector como servidor MCP, y los agentes lo consumen como cliente MCP. Para el simulador no cambia nada: sigue recibiendo las mismas peticiones HTTP, desde el conector.

En los dos casos:
- **solo las tools de lectura** están disponibles para los agentes de investigación
- la tool que escribe en el ITSM la usa solo el agente de reporte, o el código
- **las respuestas de las tools son datos:** si un log contiene instrucciones, el agente no debe obedecerlas
- **limiten el tamaño de lo que devuelve una tool,** por ejemplo a 200 líneas de log, para no saturar el contexto del modelo

---

## 10. Esqueleto de conector

Es un punto de partida. Muestra la conexión, **no** la detección, la investigación ni el enmascarado completo. Eso es parte del reto.

```python
import os, threading, time, requests

class SinVisibilidad(Exception):
    """No se pudo contactar al servicio (red, DNS, simulador detenido)."""

class Conector:
    def __init__(self, base=os.environ["SIM_BASE_URL"], rps=1.5):
        self.base, self.s = base.rstrip("/"), requests.Session()
        self._min_gap, self._last, self._lock = 1.0 / rps, 0.0, threading.Lock()

    def _esperar_turno(self):                      # limitador simple de peticiones por segundo
        with self._lock:
            espera = self._last + self._min_gap - time.monotonic()
            if espera > 0:
                time.sleep(espera)
            self._last = time.monotonic()

    def _req(self, method, path, timeout=10, **kw):
        self._esperar_turno()
        try:
            r = self.s.request(method, self.base + path, timeout=timeout, **kw)
        except (requests.ConnectionError, requests.Timeout) as e:
            raise SinVisibilidad(f"{method} {path}: {e}") from e
        return r.status_code, (r.json() if r.content else None)

    # lectura
    def health(self):                 return self._req("GET", "/health")[0]          # 200 o 503
    def metrics(self):                return self._req("GET", "/metrics")[1]
    def history(self, minutes=30):    return self._req("GET", "/metrics/history", params={"minutes": minutes})[1]["points"]
    def logs(self, **filtros):
        status, body = self._req("GET", "/logs", params=filtros)
        if status != 200:
            raise ValueError(body)                  # 400: parámetro inválido
        return [enmascarar(l) for l in body["lines"]]
    def changes(self, since=None):    return self._req("GET", "/changes", params={"since": since} if since else None)[1]["changes"]
    def calendar(self):               return self._req("GET", "/calendar")[1]["scheduled"]
    # escritura (solo ITSM)
    def crear_incidente(self, ticket):     return self._req("POST", "/itsm/incidents", json=ticket)
    def actualizar(self, inc_id, cambios): return self._req("POST", f"/itsm/incidents/{inc_id}/update", json=cambios)

def enmascarar(linea: str) -> str:
    ...  # completar: correos, contraseñas, tokens Bearer/JWT, tarjetas, IP de clientes
```

---

## 11. Práctica y evaluación

| | Práctica | Evaluación |
|---|---|---|
| Simulador | El suyo, en su máquina (`localhost`) | El del jurado, en otra máquina |
| URL | `http://localhost:8080` | La que entrega el jurado |
| Escenarios | Los de práctica y los suyos, elegidos al arrancar | Ocultos, en momentos aleatorios |
| API | La de `servicio.md` | **Exactamente la misma** |
| `verificar_conexion.py` | Con `--probar-itsm` | **Sin** `--probar-itsm` |

**Antes de la evaluación:**
1. Conecten su máquina a la red que indique la organización.
2. Ejecuten `python verificar_conexion.py --url <URL del jurado> --maas` desde la máquina donde correrá su sistema, y confirmen que hay 0 fallas.
3. Configuren `SIM_BASE_URL` con esa URL y arranquen su sistema.

---

## 12. Lista de comprobación

- [ ] `verificar_conexion.py` termina con **0 fallas** contra su simulador de práctica, incluida la sección de MaaS.
- [ ] Toda la comunicación con el servicio pasa por un único conector.
- [ ] La URL y las credenciales se leen de variables de entorno. No hay ninguna escrita en el código.
- [ ] Todas las peticiones tienen timeout.
- [ ] El conector limita las peticiones por segundo.
- [ ] Los logs se enmascaran **en el conector**, antes de llegar al monitor o a los agentes.
- [ ] Los logs se piden de forma incremental, usando la hora del servicio como cursor y eliminando duplicados.
- [ ] El código no falla si `/metrics` trae `up: 0` y le faltan campos.
- [ ] Su sistema distingue "servicio caído" de "sin visibilidad". Pruébenlo deteniendo el simulador.
- [ ] El `id` de cada incidente se guarda en el estado del sistema y sobrevive a un reinicio.
- [ ] Su sistema sigue funcionando si el simulador se reinicia mientras corre.
