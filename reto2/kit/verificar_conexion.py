#!/usr/bin/env python3
"""Verifica la conexión de su sistema con el servicio a monitorear (y, opcionalmente, con MaaS).

Ejecútelo desde la MISMA máquina y red donde correrá su sistema de agentes, con la misma URL:

    python verificar_conexion.py --url http://localhost:8080
    SIM_BASE_URL=http://10.0.5.20:8081 python verificar_conexion.py          # URL del jurado
    python verificar_conexion.py --url http://localhost:8080 --maas           # también prueba MaaS
    python verificar_conexion.py --url http://localhost:8080 --probar-itsm    # crea un ticket SEV4 de prueba

Solo usa la biblioteca estándar. Hace unas 15 peticiones al servicio, muy por debajo del límite.
Termina con código 0 si todo está bien, 1 si hay advertencias y 2 si hay fallas.

IMPORTANTE: no use --probar-itsm contra el simulador del jurado: el ticket de prueba quedaría
registrado como parte de su evaluación.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

OK, WARN, FAIL = "OK", "ADVERTENCIA", "FALLA"
results: list[tuple[str, str, str]] = []

METRIC_KEYS = ["timestamp", "up", "version", "requests_per_min", "error_rate", "errors_by_endpoint",
               "latency_p50_ms", "latency_p95_ms", "cpu_pct", "memory_mb", "memory_limit_mb",
               "disk_used_pct", "db_pool_active", "db_pool_max", "db_pool_waiting",
               "cache_hit_rate", "restarts_total"]


def report(status: str, check: str, detail: str = ""):
    results.append((status, check, detail))
    mark = {"OK": "✔", "ADVERTENCIA": "!", "FALLA": "✘"}[status]
    print(f"  {mark} {check}" + (f": {detail}" if detail else ""), flush=True)


def call(base: str, path: str, method: str = "GET", body: dict | None = None, timeout: float = 10.0,
         headers: dict | None = None):
    """Devuelve (status, json|texto, segundos). status=None si no hubo conexión."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    except (urllib.error.URLError, socket.timeout, ConnectionError, TimeoutError) as e:
        reason = getattr(e, "reason", e)
        return None, f"{type(reason).__name__}: {reason}", time.time() - t0
    try:
        return status, json.loads(raw or b"null"), time.time() - t0
    except json.JSONDecodeError:
        return status, raw.decode(errors="replace")[:200], time.time() - t0


# --------------------------------------------------------------------------- servicio
def check_service(base: str, probar_itsm: bool):
    print(f"\n[1] Alcance de red: {base}")
    status, body, secs = call(base, "/health", timeout=5)
    if status is None:
        report(FAIL, "No se puede conectar con el servicio", body)
        print("      Revise la URL, el puerto, que el simulador esté en marcha y el firewall."
              "\n      Si el simulador corre en otra máquina, no use localhost.")
        return
    report(OK, "Conexión establecida", f"{secs * 1000:.0f} ms")
    if secs > 1:
        report(WARN, "Latencia de red alta", f"{secs:.1f} s: use timeouts de al menos 10 s")

    print("\n[2] Servicio")
    if status == 200 and body == {"status": "UP"}:
        report(OK, "GET /health", "200 UP")
    elif status == 503:
        report(WARN, "GET /health", "503 DOWN: el servicio está caído en este momento (la conexión sí funciona)")
    else:
        report(FAIL, "GET /health", f"respuesta inesperada {status}: {body}")
    status, body, _ = call(base, "/health/deep")
    if status in (200, 503) and isinstance(body, dict) and "status" in body:
        comps = ", ".join(f"{k}={v.get('status')}" for k, v in (body.get("components") or {}).items())
        report(OK, "GET /health/deep", f"{status} {body['status']} ({comps or 'servicio caído'})")
    else:
        report(FAIL, "GET /health/deep", f"respuesta inesperada {status}: {body}")

    print("\n[3] Métricas")
    status, m, _ = call(base, "/metrics")
    server_ts = None
    if status != 200 or not isinstance(m, dict):
        report(FAIL, "GET /metrics", f"{status}: {m}")
    elif m.get("up") == 0:
        report(WARN, "GET /metrics", "up=0: el servicio está caído; las demás métricas no están disponibles ahora")
        server_ts = m.get("timestamp")
    else:
        missing = [k for k in METRIC_KEYS if k not in m]
        report(FAIL if missing else OK, "GET /metrics",
               f"faltan campos: {missing}" if missing else
               f"versión {m['version']}, error_rate={m['error_rate']}, p95={m['latency_p95_ms']} ms")
        server_ts = m.get("timestamp")

    if server_ts:
        try:
            skew = (datetime.now(timezone.utc) - datetime.fromisoformat(server_ts)).total_seconds()
            if abs(skew) > 5:
                report(WARN, "Reloj", f"su reloj y el del servicio difieren {skew:+.0f} s: use el 'timestamp' "
                                      "de /metrics como referencia de tiempo, no su reloj local")
            else:
                report(OK, "Reloj", f"diferencia con el servicio {skew:+.1f} s")
        except ValueError:
            report(WARN, "Reloj", f"timestamp no interpretable: {server_ts}")

    status, h, _ = call(base, "/metrics/history?minutes=60")
    if status == 200 and isinstance(h, dict) and isinstance(h.get("points"), list):
        pts = h["points"]
        detail = f"{len(pts)} puntos cada {h.get('interval_s')} s"
        if len(pts) < 30:
            detail += " (poco histórico: el simulador arrancó hace poco; la línea base será menos precisa)"
        report(OK if len(pts) >= 30 else WARN, "GET /metrics/history", detail)
    else:
        report(FAIL, "GET /metrics/history", f"{status}: {h}")

    print("\n[4] Logs")
    status, lg, _ = call(base, "/logs?limit=50")
    if status == 200 and isinstance(lg, dict) and "lines" in lg:
        report(OK, "GET /logs", f"{lg['count']} líneas disponibles, {len(lg['lines'])} devueltas")
        sample = " ".join(lg["lines"])
        if "@" in sample or "password=" in sample:
            report(WARN, "Datos sensibles", "los logs llegan SIN enmascarar (es lo esperado): "
                                            "enmascárelos en su conector antes de usarlos")
    else:
        report(FAIL, "GET /logs", f"{status}: {lg}")
    if server_ts:
        q = urllib.parse.urlencode({"since": server_ts, "level": "WARN", "limit": 10})
        status, lg, _ = call(base, f"/logs?{q}")
        report(OK if status == 200 else FAIL, "Logs incrementales (since con zona horaria, codificado)",
               f"{status}" + ("" if status == 200 else f": {lg}"))
    for bad, why in (("/logs?level=CRITICO", "nivel inválido"), ("/logs?since=ayer", "fecha inválida")):
        status, _, _ = call(base, bad)
        report(OK if status == 400 else WARN, f"Errores controlados ({why})",
               f"responde {status}" + ("" if status == 400 else ": se esperaba 400; maneje esta respuesta"))

    print("\n[5] Contexto operativo")
    for path, key in (("/dependencies", None), ("/changes", "changes"), ("/calendar", "scheduled")):
        status, body, _ = call(base, path)
        ok = status == 200 and isinstance(body, dict) and (key is None or isinstance(body.get(key), list))
        n = len(body) if key is None and isinstance(body, dict) else len(body.get(key, [])) if ok else 0
        report(OK if ok else FAIL, f"GET {path}", f"{n} elementos" if ok else f"{status}: {body}")

    print("\n[6] Gestión de incidentes (ITSM)")
    status, body, _ = call(base, "/itsm/incidents")
    if status == 200 and isinstance(body, dict):
        report(OK, "GET /itsm/incidents", f"{len(body.get('incidents', []))} incidentes registrados")
    else:
        report(FAIL, "GET /itsm/incidents", f"{status}: {body}")
    status, body, _ = call(base, "/itsm/incidents", "POST", {"title": "x", "severity": "URGENTE", "summary": "x"})
    report(OK if status == 400 else FAIL, "Validación del ITSM (severidad inválida → 400)",
           f"responde {status}" + (f", campos permitidos: {body.get('severity_allowed')}" if isinstance(body, dict) else ""))
    if probar_itsm:
        ticket = {"title": "[PRUEBA] Verificación de conexión", "severity": "SEV4",
                  "summary": "Ticket de prueba creado por verificar_conexion.py", "source": "verificar_conexion"}
        status, inc, _ = call(base, "/itsm/incidents", "POST", ticket)
        if status == 201 and isinstance(inc, dict):
            s2, upd, _ = call(base, f"/itsm/incidents/{inc['id']}/update", "POST",
                              {"status": "RESOLVED", "note": "Prueba de conexión: cerrar"})
            report(OK if s2 == 200 else FAIL, "Crear y cerrar un ticket de prueba",
                   f"{inc['id']} → {upd.get('status') if isinstance(upd, dict) else s2}")
        else:
            report(FAIL, "Crear un ticket de prueba", f"{status}: {inc}")

    print("\n[7] Prueba sintética del servicio")
    status, body, secs = call(base, "/api/checkout", "POST", {}, timeout=10)
    if status in (200, 201):
        report(OK, "POST /api/checkout", f"{status} en {secs * 1000:.0f} ms")
    elif status is None:
        report(FAIL, "POST /api/checkout", body)
    else:
        report(WARN, "POST /api/checkout", f"{status} en {secs * 1000:.0f} ms: puede ser una falla real del "
                                           "servicio en este momento (la conexión funciona)")


# --------------------------------------------------------------------------- MaaS
def check_maas():
    print("\n[8] Huawei Cloud MaaS")
    url = os.environ.get("MAAS_ENDPOINT", "https://api-ap-southeast-1.modelarts-maas.com/v2/chat/completions")
    key, model = os.environ.get("MAAS_API_KEY"), os.environ.get("MAAS_MODEL", "glm-5.2")
    if not key:
        report(FAIL, "MAAS_API_KEY", "no está definida en el entorno")
        return
    report(OK, "Configuración", f"modelo {model}, endpoint {urllib.parse.urlparse(url).netloc}")
    ctx = ssl.create_default_context()
    if os.environ.get("MAAS_VERIFY_SSL", "true").lower() == "false":
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE

    def chat(body):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
                return r.status, json.loads(r.read()), time.time() - t0
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(errors="replace")[:300], time.time() - t0
        except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
            return None, str(getattr(e, "reason", e)), time.time() - t0

    status, body, secs = chat({"model": model, "max_tokens": 20,
                               "messages": [{"role": "user", "content": "Responde solo: OK"}]})
    if status != 200:
        hint = {401: "clave inválida", 403: "sin permiso para el modelo", 404: "modelo o endpoint incorrecto",
                429: "límite de uso alcanzado"}.get(status, "revise red, proxy o certificado")
        report(FAIL, "Llamada al modelo", f"{status}: {hint}. {body}")
        return
    report(OK, "Llamada al modelo", f"respondió en {secs:.1f} s")

    tool = {"type": "function", "function": {
        "name": "get_metrics", "description": "Devuelve las métricas actuales del servicio orders-api.",
        "parameters": {"type": "object", "properties": {}, "required": []}}}
    status, body, secs = chat({"model": model, "max_tokens": 200, "tools": [tool],
                               "messages": [{"role": "user", "content": "Consulta las métricas actuales del servicio usando la herramienta."}]})
    if status == 200:
        msg = (body.get("choices") or [{}])[0].get("message", {})
        if msg.get("tool_calls"):
            report(OK, "Function calling (tools)", f"el modelo pidió la tool {msg['tool_calls'][0]['function']['name']}")
        else:
            report(WARN, "Function calling (tools)", "el endpoint acepta 'tools', pero el modelo no la pidió en esta prueba")
    else:
        report(WARN, "Function calling (tools)", f"{status}: el endpoint no acepta 'tools'; pase el contexto en el "
                                                 "mensaje o use otro modelo")


def main() -> int:
    ap = argparse.ArgumentParser(description="Verifica la conexión con el servicio a monitorear")
    ap.add_argument("--url", default=os.environ.get("SIM_BASE_URL", "http://localhost:8080"),
                    help="URL base del servicio (o variable SIM_BASE_URL)")
    ap.add_argument("--maas", action="store_true", help="probar también la conexión con Huawei Cloud MaaS")
    ap.add_argument("--probar-itsm", action="store_true",
                    help="crear y cerrar un ticket SEV4 de prueba (solo en su simulador de práctica)")
    args = ap.parse_args()
    base = args.url.rstrip("/")

    print("Verificación de conexión · Reto 2")
    check_service(base, args.probar_itsm)
    if args.maas:
        check_maas()

    fails = sum(1 for r in results if r[0] == FAIL)
    warns = sum(1 for r in results if r[0] == WARN)
    print(f"\nResultado: {len(results) - fails - warns} OK · {warns} advertencias · {fails} fallas")
    if fails:
        print("Corrija las fallas antes de conectar su sistema.")
    elif warns:
        print("La conexión funciona. Lea las advertencias: su sistema debe manejar esos casos.")
    else:
        print("Todo listo: su sistema puede conectarse con esta URL.")
    return 2 if fails else 1 if warns else 0


if __name__ == "__main__":
    raise SystemExit(main())
