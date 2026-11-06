# Simulador de orders-api

Simula el servicio `orders-api`, su plataforma de observabilidad y un sistema de tickets (ITSM). Solo necesita Python 3.9 o superior, sin instalar nada.

```bash
python simulador.py                       # servicio sano en http://localhost:8080
python simulador.py --speed 5             # los escenarios avanzan 5 veces más rápido
python simulador.py --scenario escenarios/practica-cache-caida.json --delay 300
                                          # la falla empieza en 5 minutos
```

El escenario se elige al arrancar. Para probar otro, detenga el simulador y vuelva a iniciarlo con el nuevo `--scenario`. Use `--delay` para que su sistema tenga tiempo de calcular la línea base antes de la falla.

La consola del simulador muestra las marcas del escenario, por ejemplo `[escenario] marca 'fault_start' a las 14:03:10`. Compárenlas con la hora a la que su sistema creó el incidente para medir su tiempo de detección. Las marcas no se exponen por la API.

La referencia completa de la API está en `../servicio.md`.

## Escenarios de práctica

| Archivo | Qué pasa |
|---|---|
| `practica-cache-caida.json` | Redis deja de responder durante 15 minutos |
| `practica-fuga-memoria.json` | Un release con fuga de memoria provoca reinicios por OOM |

En la evaluación, el jurado usará **otros escenarios** que ustedes no conocen.

## Crear sus propios escenarios

Se recomienda crear escenarios propios para probar su sistema. Un escenario es un JSON con pasos (`steps`). `at` es el segundo del escenario en el que se aplica cada paso.

| Paso | Ejemplo | Efecto |
|---|---|---|
| `ramp` | `{"ramp": {"lat_p95": {"to": 2000, "over": 120}}}` | Lleva una métrica a un valor, de forma gradual |
| `set` | `{"set": {"err_checkout": 0.5}}` | Fija una métrica de inmediato |
| `log` | `{"log": {"level": "ERROR", "logger": "c.o.x", "msg": "...", "every": 5, "until": 600}}` | Emite un log una vez, o cada `every` segundos hasta `until` |
| `deps` | `{"deps": {"cache": "DOWN"}}` | Cambia el estado de una dependencia |
| `status_codes` | `{"status_codes": {"checkout": 502}}` | Código HTTP de los errores de un endpoint |
| `change` | `{"change": {"id": "CHG-1", "type": "deploy", "description": "...", "version": "3.2.0"}}` | Registra un cambio |
| `restart` | `{"restart": {"downtime": 20, "reset": ["mem_mb"], "logs": [...]}}` | El servicio cae y se reinicia |
| `recover` | `{"recover": true}` | Vuelve todo a la normalidad |
| `mark` | `{"mark": "fault_start"}` | Marca de tiempo para medir el tiempo de detección |

**Métricas que se pueden modificar:** `rpm`, `lat_p50`, `lat_p95`, `cpu`, `mem_mb`, `disk_pct`, `pool_active`, `pool_waiting`, `cache_hit`, `err_products`, `err_orders`, `err_checkout`.

**Marcadores que se pueden usar en `msg`:** `{email}`, `{ip}`, `{order}`, `{n}`, `{uuid}`, `{card}`, `{jwt}`, `{ms}`, `{mem}`, `{disk}`, `{pool}`, `{waiting}`, `{version}`.

Un escenario también puede incluir entradas de `calendar` con `at`, `duration`, `name`, `owner` y `expected_impact`.
