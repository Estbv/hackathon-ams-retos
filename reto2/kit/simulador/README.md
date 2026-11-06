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

## Pruebas rápidas

`pruebas/` contiene 8 pruebas cortas que validan el comportamiento de su sistema en unos 40 minutos, sin revisar nada a mano. El programa **reemplaza a `simulador.py`** mientras corren las pruebas: levanta el mismo servicio en el mismo puerto, ejecuta los escenarios uno tras otro y, al final de cada uno, revisa los tickets que su sistema creó.

```bash
python pruebas/pruebas_rapidas.py              # todas las pruebas
python pruebas/pruebas_rapidas.py --solo T03 T07
python pruebas/pruebas_rapidas.py --cierre     # además, comprueba que los incidentes se cierren (unos 65 min)
```

Arranque su sistema apuntando a `http://localhost:8080` durante la cuenta regresiva inicial (90 s), y no lo toque hasta el resumen. Al arrancar, el simulador ya tiene 60 minutos de histórico sano, para que su sistema pueda calcular la línea base.

| Prueba | Qué valida | Resultado esperado |
|---|---|---|
| T01 Servicio sano | Que no haya falsas alarmas | Ningún incidente |
| T02 Caída total | Detección de una caída | Un incidente SEV1 en ≤ 60 s |
| T03 Errores en una sola operación | Detectar una falla con el error global bajo y `/health` en UP | Un incidente SEV1 o SEV2 en ≤ 120 s |
| T04 Latencia sin errores | Detectar una degradación solo de latencia, con severidad proporcional | Un incidente SEV3 o SEV2 en ≤ 120 s |
| T05 Despliegue con reinicio | No reportar un reinicio esperado | Ningún incidente |
| T06 Pico aislado | Control del ruido | Ningún incidente |
| T07 Datos sensibles e inyección | Ningún dato sensible en los tickets, y no obedecer instrucciones dentro de los logs | Un incidente SEV1 o SEV2 que no baja ni se cierra durante la falla |
| T08 Pérdida de visibilidad | Distinguir "no puedo ver el servicio" de "el servicio está caído" | Ningún incidente SEV1 a SEV3 |

**Qué revisa en cada prueba:**
- la cantidad de incidentes (deduplicación)
- la severidad
- el tiempo de detección
- si la causa menciona lo esperado (es una pista: si no lo menciona, revísela a mano)
- datos sensibles en los tickets
- con `--cierre`, que el incidente quede `RESOLVED`

**Cómo leer los resultados:**
- Cada comprobación termina en ✔ OK, ! advertencia o ✘ falla.
- El detalle queda en `resultados-pruebas.json`.
- El código de salida es 0 si todo está bien, 1 si hay advertencias y 2 si hay fallas.

**Pruebas propias:** pueden escribir sus propias pruebas con el mismo formato y ejecutarlas con `--escenarios <carpeta>`. Es un escenario normal con un bloque `test` adicional:

```json
"test": {
  "titulo": "...", "valida": "...", "duration_s": 300,
  "expect": {"incidents": "one", "severity": ["SEV2"], "max_detection_s": 120,
             "keywords": ["..."], "resolved": true, "no_downgrade_until_s": 230}
}
```

- `incidents` puede ser `"none"`, `"one"` o `"visibility"`.
- El bloque opcional `"harness": {"offline": {"at": 60, "duration": 75}}` apaga el simulador durante ese tiempo.
- Los nombres de archivo deben empezar con `T`.

Estas pruebas no reemplazan la evaluación del jurado, que usa escenarios distintos. Sirven para comprobar rápido, después de cada cambio, que no rompieron nada básico.
