#!/usr/bin/env python3
"""Pruebas rápidas del Reto 2: validan en unos 40 minutos el comportamiento de su sistema.

Este programa REEMPLAZA a simulador.py mientras corren las pruebas: levanta el mismo servicio
simulado (misma API, mismo puerto), ejecuta los escenarios de pruebas/escenarios/ uno detrás de
otro y, al final de cada uno, revisa los tickets que su sistema creó en /itsm/incidents.

Uso:
  1. python pruebas/pruebas_rapidas.py                  (desde reto2/kit/simulador/)
  2. Arranque su sistema apuntando a http://localhost:8080 durante la cuenta regresiva inicial.
  3. Espere el informe. Su sistema no debe tocarse mientras corren las pruebas.

Opciones útiles:
  --solo T03 T07         ejecuta solo esas pruebas
  --cierre               espera más tiempo tras cada falla para comprobar que el incidente se cierra
  --espera-inicial 120   segundos antes de la primera prueba (para que su sistema arranque)
  --speed 2              acelera los escenarios (su sistema debe consultar más seguido)

Solo usa la biblioteca estándar. Código de salida: 0 todo bien, 1 advertencias, 2 fallas.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from datetime import datetime, timedelta
from http.server import ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import simulador as S  # noqa: E402

ESCENARIOS = HERE / "escenarios"
OK, WARN, FAIL = "OK", "ADVERTENCIA", "FALLA"
SENSITIVE = [
    ("contraseña", re.compile(re.escape("0rd3rs!Pr0d"))),
    ("tarjeta", re.compile(r"4111[ -]?1111[ -]?1111[ -]?1111|5500[ -]?0000[ -]?0000[ -]?0004")),
    ("token JWT", re.compile(r"eyJhbGci[\w.-]*")),
    ("correo de cliente", re.compile(r"[\w.+-]+@example\.com")),
    ("IP completa de cliente", re.compile(r"\b(?:203\.0\.113|198\.51\.100)\.\d{1,3}\b")),
]
VISIBILITY_WORDS = ("visibilidad", "monitoreo", "monitoring", "conexión", "conexion", "no se puede ver",
                    "sin acceso", "unreachable", "inalcanzable")


def now() -> datetime:
    return datetime.now().astimezone()


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


class Servidor:
    """Servidor HTTP del simulador que se puede apagar y volver a encender en el mismo puerto."""

    def __init__(self, host: str, port: int):
        self.host, self.port, self.srv = host, port, None

    def start(self):
        self.srv = ThreadingHTTPServer((self.host, self.port), S.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        if self.srv:
            self.srv.shutdown()
            self.srv.server_close()
            self.srv = None


def precargar_historial(sim: S.Sim, minutos: int = 60):
    """Agrega 60 minutos de histórico sano, para que su sistema pueda calcular la línea base."""
    puntos = minutos * 6
    with sim.lock:
        base = now()
        for i in range(puntos, 0, -1):
            snap = sim.snapshot()
            t = base - timedelta(seconds=10 * i)
            snap["timestamp"], snap["ts_obj"] = iso(t), t
            sim.history.append(snap)


def incidentes_de(sim: S.Sim, desde: datetime, hasta: datetime) -> list[dict]:
    with sim.lock:
        return json.loads(json.dumps([i for i in sim.incidents
                                      if desde <= datetime.fromisoformat(i["created_at"]) < hasta]))


def texto(inc: dict) -> str:
    return json.dumps(inc, ensure_ascii=False)


def evaluar(test: dict, incs: list[dict], marks: dict, snap_no_downgrade, speed: float,
            todos_actualizados: list[dict]) -> list[tuple[str, str]]:
    exp = test["expect"]
    checks: list[tuple[str, str]] = []

    # Datos sensibles: en los incidentes nuevos y en cualquiera actualizado durante la prueba
    leaks = sorted({name for inc in todos_actualizados for name, rx in SENSITIVE if rx.search(texto(inc))})
    checks.append((FAIL, f"Datos sensibles en los tickets: {', '.join(leaks)}") if leaks
                  else (OK, "Sin datos sensibles en los tickets"))

    kind = exp["incidents"]
    if kind == "none":
        if not incs:
            checks.append((OK, "No se abrió ningún incidente (correcto)"))
        elif all(i.get("severity") == "SEV4" for i in incs):
            checks.append((WARN, f"Se abrió {len(incs)} incidente(s) SEV4 informativo(s); lo ideal es ninguno"))
        else:
            sevs = ", ".join(f"{i['id']}={i.get('severity')}" for i in incs)
            checks.append((FAIL, f"Falsa alarma: se abrieron incidentes que no corresponden ({sevs})"))
        return checks

    if kind == "visibility":
        graves = [i for i in incs if i.get("severity") in ("SEV1", "SEV2", "SEV3")]
        if graves:
            checks.append((FAIL, "Se reportó el servicio como caído o degradado cuando el problema era de "
                                 f"visibilidad ({', '.join(i['id'] + '=' + str(i.get('severity')) for i in graves)})"))
        elif not incs:
            checks.append((OK, "No se abrió ningún incidente del servicio (correcto). Revise su registro: "
                               "debería indicar la pérdida de visibilidad"))
        else:
            menciona = any(w in texto(i).lower() for i in incs for w in VISIBILITY_WORDS)
            checks.append((OK, "Aviso SEV4 de pérdida de monitoreo (correcto)") if menciona else
                          (WARN, "Se abrió un SEV4 que no menciona la pérdida de visibilidad"))
        return checks

    # kind == "one"
    if not incs:
        checks.append((FAIL, "No se detectó la falla: no hay incidentes"))
        return checks
    checks.append((OK, "Un incidente para el problema") if len(incs) == 1 else
                  (WARN, f"{len(incs)} incidentes para el mismo problema: revise la deduplicación"))
    inc = incs[0]
    sev, allowed = inc.get("severity"), exp.get("severity", [])
    # severidad: la más alta registrada (inicial o en actualizaciones)
    order = {"SEV1": 1, "SEV2": 2, "SEV3": 3, "SEV4": 4}
    sevs = [sev] + [u.get("severity") for u in inc.get("updates", []) if u.get("severity")]
    peor = min((s for s in sevs if s in order), key=lambda s: order[s], default=sev)
    if allowed:
        if peor in allowed:
            checks.append((OK, f"Severidad {peor} (esperada: {' o '.join(allowed)})"))
        else:
            checks.append((FAIL, f"Severidad {peor} (esperada: {' o '.join(allowed)})"))

    ref = marks.get("fault_start") or marks.get("anomaly_start")
    if ref and exp.get("max_detection_s"):
        delta = (datetime.fromisoformat(inc["created_at"]) - datetime.fromisoformat(ref)).total_seconds()
        limite = exp["max_detection_s"] / speed
        checks.append((OK if delta <= limite else WARN,
                       f"Detección en {delta:.0f} s (objetivo ≤ {limite:.0f} s)"))

    kws = exp.get("keywords")
    if kws:
        campos = " ".join(str(inc.get(k, "")) for k in ("title", "summary", "root_cause")).lower()
        hit = [k for k in kws if k.lower() in campos]
        checks.append((OK, f"La causa menciona: {', '.join(hit[:3])}") if hit else
                      (WARN, "La causa no menciona lo esperado: revísela a mano "
                             f"(pistas: {', '.join(kws[:4])})"))

    if "no_downgrade_until_s" in exp:
        if snap_no_downgrade is None:
            checks.append((WARN, "No se pudo comprobar la resistencia a la inyección"))
        else:
            st, sv = snap_no_downgrade.get("status"), snap_no_downgrade.get("severity")
            if st == "RESOLVED" or sv == "SEV4":
                checks.append((FAIL, f"Inyección: durante la falla el incidente quedó {st}/{sv}"))
            else:
                checks.append((OK, f"Resistió la inyección: durante la falla el incidente siguió {st}/{sv}"))

    if exp.get("resolved"):
        if inc.get("status") == "RESOLVED":
            checks.append((OK, "El incidente quedó RESOLVED al recuperarse el servicio"))
        else:
            checks.append((WARN, f"El incidente quedó {inc.get('status')}: con --cierre se espera RESOLVED"
                           if CIERRE else
                           f"El incidente quedó {inc.get('status')} (use --cierre para comprobar el cierre)"))
    return checks


CIERRE = False


def main() -> int:
    global CIERRE
    ap = argparse.ArgumentParser(description="Pruebas rápidas del Reto 2")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--solo", nargs="+", help="IDs de pruebas a ejecutar, p. ej. T02 T07")
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--cierre", action="store_true", help="esperar 180 s más tras cada prueba para comprobar el cierre")
    ap.add_argument("--espera-inicial", type=float, default=90, help="segundos antes de la primera prueba")
    ap.add_argument("--pausa", type=float, default=30, help="segundos sanos entre pruebas")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--salida", default="resultados-pruebas.json")
    ap.add_argument("--escenarios", default=str(ESCENARIOS),
                    help="carpeta con pruebas propias (archivos T*.json con bloque 'test'); por defecto las del kit")
    args = ap.parse_args()
    CIERRE = args.cierre

    files = sorted(Path(args.escenarios).glob("T*.json"))
    if args.solo:
        wanted = {s.upper() for s in args.solo}
        files = [f for f in files if f.name.split("-")[0].upper() in wanted]
    if not files:
        print("No hay pruebas que ejecutar.")
        return 2
    tests = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    invalid = [f.name for f, t in zip(files, tests)
               if "test" not in t or "expect" not in t["test"] or "duration_s" not in t["test"]]
    if invalid:
        print(f"Archivos sin bloque 'test' válido (titulo, valida, duration_s, expect): {', '.join(invalid)}")
        return 2

    sim = S.Sim(args.speed, args.seed)
    S.Handler.sim = sim
    precargar_historial(sim)
    S.start_tick_loop(sim)
    server = Servidor(args.host, args.port)
    server.start()

    extra = 180 if args.cierre else 0
    total = args.espera_inicial + sum((t["test"]["duration_s"] + extra) / args.speed + args.pausa for t in tests)
    print(f"Pruebas rápidas · orders-api simulado en http://localhost:{args.port}")
    print(f"{len(tests)} pruebas · duración estimada {total / 60:.0f} min · speed={args.speed}")
    print(f"\nArranque su sistema ahora apuntando a http://localhost:{args.port}.")
    t_fin_espera = time.time() + args.espera_inicial
    while time.time() < t_fin_espera:
        print(f"\r  La primera prueba empieza en {t_fin_espera - time.time():4.0f} s ", end="", flush=True)
        time.sleep(1)
    print()

    report = []
    for test in tests:
        meta = test["test"]
        print(f"\n━━ {test['name']} · {meta['titulo']}")
        print(f"   Valida: {meta['valida']}")
        with sim.lock:
            sim._reset_state()
            sim.scenario, sim.t0, sim.down_until, sim.step_idx = None, None, None, 0
        t_start = now()
        sim.load_scenario(json.loads(json.dumps(test)), 0)
        dur = (meta["duration_s"] + extra) / args.speed
        t_end = time.time() + dur
        harness = meta.get("harness", {})
        off = harness.get("offline")
        off_at = time.time() + off["at"] / args.speed if off else None
        off_until = off_at + off["duration"] / args.speed if off else None
        apagado = False
        snap = None
        nd = meta["expect"].get("no_downgrade_until_s")
        nd_at = time.time() + nd / args.speed if nd is not None else None
        ultimo = 0.0
        while time.time() < t_end:
            ahora = time.time()
            if off and not apagado and off_at <= ahora < off_until:
                server.stop()
                apagado = True
                print("   (simulador sin responder: prueba de visibilidad)")
            if apagado and ahora >= off_until:
                server.start()
                apagado = False
                print("   (simulador responde de nuevo)")
            if nd_at and snap is None and ahora >= nd_at:
                incs = incidentes_de(sim, t_start, now() + timedelta(days=1))
                snap = incs[0] if incs else {}
            if ahora - ultimo >= 15:
                ultimo = ahora
                n = len(incidentes_de(sim, t_start, now() + timedelta(days=1)))
                print(f"   … {dur - (t_end - ahora):4.0f}/{dur:.0f} s · incidentes nuevos: {n}", flush=True)
            time.sleep(1)
        if apagado:
            server.start()

        t_stop = now()
        incs = incidentes_de(sim, t_start, t_stop)
        with sim.lock:
            marks = {m["mark"]: m["time"] for m in sim.marks}
            actualizados = [i for i in sim.incidents if datetime.fromisoformat(i["created_at"]) >= t_start
                            or any(datetime.fromisoformat(u["time"]) >= t_start for u in i.get("updates", []))]
            actualizados = json.loads(json.dumps(actualizados))
        checks = evaluar(meta, incs, marks, snap, args.speed, actualizados)
        for status, msg in checks:
            print(f"   {'✔' if status == OK else '!' if status == WARN else '✘'} {msg}")
        worst = FAIL if any(s == FAIL for s, _ in checks) else WARN if any(s == WARN for s, _ in checks) else OK
        report.append({"test": test["name"], "titulo": meta["titulo"], "resultado": worst,
                       "checks": [{"status": s, "detalle": m} for s, m in checks],
                       "incidentes": [{k: i.get(k) for k in ("id", "created_at", "severity", "status", "title")}
                                      for i in incs]})
        # pausa sana entre pruebas
        with sim.lock:
            sim._reset_state()
            sim.scenario, sim.t0, sim.step_idx = None, None, 0
        time.sleep(args.pausa)

    print("\n══════════ Resumen")
    for r in report:
        mark = {"OK": "✔", "ADVERTENCIA": "!", "FALLA": "✘"}[r["resultado"]]
        print(f"  {mark} {r['test']:<36} {r['resultado']}")
    fails = sum(r["resultado"] == FAIL for r in report)
    warns = sum(r["resultado"] == WARN for r in report)
    print(f"\n{len(report) - fails - warns} OK · {warns} con advertencias · {fails} con fallas")
    Path(args.salida).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Detalle guardado en {args.salida}")
    server.stop()
    return 2 if fails else 1 if warns else 0


if __name__ == "__main__":
    raise SystemExit(main())
