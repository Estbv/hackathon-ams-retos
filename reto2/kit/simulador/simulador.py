#!/usr/bin/env python3
"""Simulador de "orders-api" para el Reto 2 (monitoreo autónomo con agentes).

Simula un servicio en producción y la plataforma de observabilidad que lo rodea:
  - el servicio:          /health, /health/deep, /api/products/{id}, /api/orders/{id}, POST /api/checkout
  - observabilidad:       /metrics, /metrics/history, /logs, /dependencies, /changes, /calendar
  - gestión de tickets:   /itsm/incidents (donde los agentes reportan)

Las fallas se inyectan con un archivo de escenario (JSON) que se indica al arrancar.
Ver escenarios/ y README.md. Solo usa la biblioteca estándar de Python 3.9+.

Uso:
  python simulador.py                                   # servicio sano
  python simulador.py --scenario escenarios/practica-cache-caida.json --delay 300
  python simulador.py --speed 5                         # escenarios 5 veces más rápidos
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import secrets
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

LEVELS = {"DEBUG": 0, "INFO": 1, "WARN": 2, "ERROR": 3}
BASELINE = {
    "rpm": 600.0, "lat_p50": 80.0, "lat_p95": 180.0, "cpu": 25.0, "mem_mb": 520.0, "disk_pct": 54.0,
    "pool_active": 4.0, "pool_waiting": 0.0, "cache_hit": 0.93,
    "err_products": 0.001, "err_orders": 0.002, "err_checkout": 0.003,
}
NOISE = {"rpm": 0.05, "lat_p50": 0.08, "lat_p95": 0.1, "cpu": 0.08, "mem_mb": 0.01, "disk_pct": 0.0,
         "pool_active": 0.05, "pool_waiting": 0.1, "cache_hit": 0.01}
MEM_LIMIT_MB, POOL_MAX = 1024, 20
ENDPOINTS = [("GET", "/api/products/{n}", "products", 0.60),
             ("GET", "/api/orders/ORD-{order}", "orders", 0.25),
             ("POST", "/api/checkout", "checkout", 0.15)]
FIRST = ["ana.silva", "li.wei", "maria.garcia", "john.smith", "omar.ali", "eva.novak", "lucas.perez", "sofia.rossi"]
SEVERITIES = ["SEV1", "SEV2", "SEV3", "SEV4"]


def now() -> datetime:
    return datetime.now().astimezone()


class Sim:
    def __init__(self, speed: float, seed: int | None):
        self.lock = threading.RLock()
        self.rng = random.Random(seed)
        self.speed = speed
        self.started_at = now()
        self.logs: deque = deque(maxlen=60000)
        self.history: deque = deque(maxlen=2160)  # 6 h a 10 s
        self.incidents: list[dict] = []
        self.changes = [
            {"id": "CHG-60871", "time": "2026-10-13T10:02:00", "type": "deploy", "service": "orders-api",
             "description": "Release 3.1.4: corrección de redondeo en impuestos", "by": "release.bot"},
            {"id": "CHG-60950", "time": "2026-10-16T22:30:00", "type": "infra", "service": "orders-db",
             "description": "Parche menor de PostgreSQL 15.8", "by": "dba.team"},
        ]
        self.calendar = [
            {"name": "Backup nocturno de orders-db", "schedule": "diario 02:00-02:40", "owner": "DBA",
             "expected_impact": "Latencia de escritura ligeramente mayor; sin impacto en clientes"},
        ]
        self.version = "3.1.4"
        self.pid = 4100
        self.restarts = -1  # el primer arranque no cuenta
        self._reset_state()
        self.scenario: dict | None = None
        self.t0: float | None = None
        self.step_idx = 0
        self.marks: list[dict] = []
        self.down_until: float | None = None
        self.pending_startup = False
        self._startup_logs()

    # ------------------------------------------------------------------ estado
    def _reset_state(self):
        self.values = dict(BASELINE)
        self.ramps: dict[str, tuple] = {}
        self.deps = {"database": "UP", "cache": "UP", "payment_provider": "UP"}
        self.status_codes = {"products": 500, "orders": 500, "checkout": 500}
        self.emitters: list[dict] = []

    def s(self) -> float | None:
        """Segundos de escenario transcurridos (escalados por --speed)."""
        if self.t0 is None or time.time() < self.t0:
            return None
        return (time.time() - self.t0) * self.speed

    def cur(self, key: str) -> float:
        if key in self.ramps:
            start, target, s0, over = self.ramps[key]
            s = self.s() or s0
            frac = 1.0 if over <= 0 else max(0.0, min(1.0, (s - s0) / over))
            return start + (target - start) * frac
        return self.values[key]

    def down(self) -> bool:
        return self.down_until is not None and time.time() < self.down_until

    # ------------------------------------------------------------------ logs
    def _fill(self, msg: str) -> str:
        r = self.rng

        def rep(m):
            k = m.group(1)
            return {
                "email": lambda: f"{r.choice(FIRST)}{r.randint(1, 99)}@example.com",
                "ip": lambda: f"{r.choice(['203.0.113', '198.51.100'])}.{r.randint(2, 250)}",
                "order": lambda: str(r.randint(900000, 999999)),
                "n": lambda: str(r.randint(100, 9999)),
                "uuid": lambda: str(uuid.UUID(int=r.getrandbits(128))),
                "card": lambda: r.choice(["4111 1111 1111 1111", "5500 0000 0000 0004"]),
                "jwt": lambda: "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvcmRlcnMtYXBpIn0." + secrets.token_urlsafe(16),
                "ms": lambda: str(int(self.cur("lat_p95") * r.uniform(0.7, 1.1))),
                "mem": lambda: str(int(self.cur("mem_mb"))),
                "disk": lambda: str(int(self.cur("disk_pct"))),
                "pool": lambda: str(int(min(POOL_MAX, self.cur("pool_active")))),
                "waiting": lambda: str(int(self.cur("pool_waiting"))),
                "version": lambda: self.version,
            }.get(k, lambda: m.group(0))()

        return re.sub(r"\{(\w+)\}", rep, msg)

    def app_log(self, level: str, logger: str, msg: str, thread: str | None = None):
        ts = now()
        thread = thread or f"http-nio-8080-exec-{self.rng.randint(1, 50)}"
        line = (f"{ts:%Y-%m-%d %H:%M:%S}.{ts.microsecond // 1000:03d} {level:>5} {self.pid} --- "
                f"[{thread}] {logger} : {self._fill(msg)}")
        self.logs.append({"ts": ts, "level": level, "source": "app", "line": line})

    def access_log(self, method, path, status, rt_ms):
        ts = now()
        ip = self._fill("{ip}")
        level = "ERROR" if status >= 500 else "WARN" if status >= 400 else "INFO"
        line = (f'{ip} - - [{ts:%d/%b/%Y:%H:%M:%S %z}] "{method} {self._fill(path)} HTTP/1.1" {status} '
                f'{self.rng.randint(200, 2400)} "-" "Mozilla/5.0" rt={rt_ms / 1000:.3f}')
        self.logs.append({"ts": ts, "level": level, "source": "access", "line": line})

    def _startup_logs(self):
        self.pid += self.rng.randint(3, 400)
        self.restarts += 1
        lg = "c.o.orders.OrdersApiApplication"
        self.app_log("INFO", lg, f"Starting OrdersApiApplication v{self.version} using Java 21.0.4 with PID {self.pid}", "main")
        self.app_log("INFO", "c.o.orders.config.DataSourceConfig",
                     "DataSource url=jdbc:postgresql://orders-db:5432/orders user=orders_app password=0rd3rs!Pr0d", "main")
        self.app_log("INFO", "com.zaxxer.hikari.HikariDataSource", f"HikariPool-1 - Start completed. maximumPoolSize={POOL_MAX}", "main")
        self.app_log("INFO", "c.o.orders.cache.RedisCacheClient", "Connected to Redis orders-cache:6379", "main")
        self.app_log("INFO", lg, f"Started OrdersApiApplication in {self.rng.uniform(9, 14):.1f} seconds", "main")

    # ------------------------------------------------------------------ escenario
    def load_scenario(self, data: dict, delay: float):
        with self.lock:
            self._reset_state()
            self.scenario = data
            self.t0 = time.time() + delay
            self.step_idx = 0
            self.marks = []
            data["steps"] = sorted(data.get("steps", []), key=lambda x: x["at"])
            for c in data.get("calendar", []):
                start = datetime.fromtimestamp(self.t0 + c["at"] / self.speed).astimezone()
                end = datetime.fromtimestamp(self.t0 + (c["at"] + c.get("duration", 0)) / self.speed).astimezone()
                self.calendar.append({k: v for k, v in c.items() if k not in ("at", "duration")} |
                                     {"start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds")})

    def _apply(self, st: dict):
        s = self.s() or 0.0
        if "mark" in st:
            self.marks.append({"mark": st["mark"], "time": now().isoformat(timespec="seconds")})
            # Solo en la consola del simulador (no en la API): sirve para medir el tiempo de detección.
            print(f"[escenario] marca '{st['mark']}' a las {now():%H:%M:%S}", flush=True)
        if "change" in st:
            c = dict(st["change"])
            c["time"] = now().isoformat(timespec="seconds")
            if c.get("version"):
                self.version = c["version"]
            self.changes.append(c)
        for key in ("ramp", "set"):
            for k, v in st.get(key, {}).items():
                target = v["to"] if isinstance(v, dict) else v
                over = v.get("over", 0) if isinstance(v, dict) else 0
                self.ramps[k] = (self.cur(k), float(target), s, float(over))
        self.deps.update(st.get("deps", {}))
        self.status_codes.update(st.get("status_codes", {}))
        if "log" in st:
            spec = st["log"]
            if spec.get("every"):
                self.emitters.append({"spec": spec, "next": s, "until": spec.get("until", math.inf)})
            else:
                self.app_log(spec.get("level", "INFO"), spec.get("logger", "c.o.orders"), spec["msg"], spec.get("thread"))
        if "restart" in st:
            r = st["restart"]
            for line in r.get("logs", []):
                self.app_log(line.get("level", "ERROR"), line.get("logger", "c.o.orders"), line["msg"], line.get("thread"))
            self.down_until = time.time() + r.get("downtime", 20) / self.speed
            self.pending_startup = True
            for k in r.get("reset", []):
                self.ramps.pop(k, None)
                self.values[k] = BASELINE[k]
        if st.get("recover"):
            self._reset_state()

    # ------------------------------------------------------------------ tick
    def tick(self):
        with self.lock:
            s = self.s()
            steps = self.scenario["steps"] if self.scenario else []
            while s is not None and self.step_idx < len(steps) and steps[self.step_idx]["at"] <= s:
                self._apply(steps[self.step_idx])
                self.step_idx += 1
            if self.pending_startup and not self.down():
                self.pending_startup = False
                self._startup_logs()
            if s is not None:
                for em in self.emitters:
                    while em["next"] <= s and em["next"] <= em["until"]:
                        sp = em["spec"]
                        self.app_log(sp.get("level", "INFO"), sp.get("logger", "c.o.orders"), sp["msg"], sp.get("thread"))
                        em["next"] += sp["every"]
            self._traffic()
            if not self.history or (now() - self.history[-1]["ts_obj"]).total_seconds() >= 10:
                snap = self.snapshot()
                snap["ts_obj"] = now()
                self.history.append(snap)

    def _traffic(self):
        r = self.rng
        if self.down():
            for _ in range(2):
                m, p, _, _ = r.choices(ENDPOINTS, weights=[e[3] for e in ENDPOINTS])[0]
                self.access_log(m, p, 502, 1)
            return
        n = max(1, round(self.cur("rpm") / 60 * 0.2 + r.uniform(-0.5, 0.5)))
        for _ in range(n):
            m, p, name, _ = r.choices(ENDPOINTS, weights=[e[3] for e in ENDPOINTS])[0]
            status, lat = self.simulate_request(name)
            self.access_log(m, p, status, lat)
            if name == "checkout" and status < 400 and r.random() < 0.5:
                self.app_log("INFO", "c.o.orders.web.CheckoutController",
                             f"POST /api/checkout completed in {int(lat)}ms orderId=ORD-{{order}} customer={{email}} status=201")
        if r.random() < 1 / 30:
            self.app_log("INFO", "c.o.orders.monitoring.HealthIndicator",
                         "Health check /actuator/health status=UP", "scheduling-1")

    def simulate_request(self, name: str) -> tuple[int, float]:
        p50, p95 = max(1.0, self.cur("lat_p50")), max(2.0, self.cur("lat_p95"))
        sigma = max(0.05, math.log(max(p95 / p50, 1.01)) / 1.645)
        lat = p50 * math.exp(self.rng.gauss(0, sigma))
        if self.rng.random() < self.cur(f"err_{name}"):
            return self.status_codes.get(name, 500), lat
        return (201 if name == "checkout" else 200), lat

    def snapshot(self) -> dict:
        r = self.rng
        if self.down():
            return {"timestamp": now().isoformat(timespec="seconds"), "up": 0, "service": "orders-api",
                    "version": self.version, "restarts_total": self._restarts()}

        def v(k):
            base = self.cur(k)
            return base * (1 + r.gauss(0, NOISE.get(k, 0)))

        weights = {e[2]: e[3] for e in ENDPOINTS}
        err = sum(weights[k] * self.cur(f"err_{k}") for k in weights) * (1 + r.gauss(0, 0.1))
        return {
            "timestamp": now().isoformat(timespec="seconds"), "up": 1, "service": "orders-api", "version": self.version,
            "requests_per_min": round(max(0, v("rpm"))),
            "error_rate": round(max(0.0, min(1.0, err)), 4),
            "errors_by_endpoint": {k: round(self.cur(f"err_{k}"), 4) for k in weights},
            "latency_p50_ms": round(max(1, v("lat_p50"))), "latency_p95_ms": round(max(2, v("lat_p95"))),
            "cpu_pct": round(max(0, min(100, v("cpu"))), 1),
            "memory_mb": round(max(0, min(MEM_LIMIT_MB, v("mem_mb")))), "memory_limit_mb": MEM_LIMIT_MB,
            "disk_used_pct": round(max(0, min(100, v("disk_pct"))), 1),
            "db_pool_active": int(max(0, min(POOL_MAX, round(v("pool_active"))))), "db_pool_max": POOL_MAX,
            "db_pool_waiting": int(max(0, round(v("pool_waiting")))),
            "cache_hit_rate": round(max(0, min(1, v("cache_hit"))), 3),
            "restarts_total": self._restarts(),
        }

    def _restarts(self) -> int:
        return self.restarts


# ---------------------------------------------------------------------- HTTP
class BadRequest(ValueError):
    """Parámetro inválido en la petición: se responde 400 con un mensaje claro."""


class Handler(BaseHTTPRequestHandler):
    sim: Sim = None  # type: ignore
    server_version = "orders-sim/1.0"

    def log_message(self, *a):  # silencioso
        pass

    def _send(self, code: int, body, ctype="application/json"):
        data = (json.dumps(body, ensure_ascii=False, indent=2) if ctype == "application/json" else body).encode()
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except json.JSONDecodeError:
            return {"__invalid__": True}

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def _route(self, method: str):
        sim = self.sim
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        p = u.path.rstrip("/") or "/"
        try:
            # ------------------------------------------------ servicio
            if p == "/health" and method == "GET":
                return self._send(503, {"status": "DOWN"}) if sim.down() else self._send(200, {"status": "UP"})
            if p == "/health/deep" and method == "GET":
                if sim.down():
                    return self._send(503, {"status": "DOWN"})
                with sim.lock:
                    comps = {k: {"status": v} for k, v in sim.deps.items()}
                    comps["diskSpace"] = {"status": "UP" if sim.cur("disk_pct") < 99.5 else "DOWN",
                                          "used_pct": round(sim.cur("disk_pct"), 1)}
                overall = "UP" if all(c["status"] == "UP" for c in comps.values()) else "DEGRADED"
                return self._send(200 if overall == "UP" else 503, {"status": overall, "components": comps})
            m = re.fullmatch(r"/api/(products|orders)/[\w-]+", p)
            if (m and method == "GET") or (p == "/api/checkout" and method == "POST"):
                name = m.group(1) if m else "checkout"
                if sim.down():
                    return self._send(503, {"error": "service unavailable"})
                with sim.lock:
                    status, lat = sim.simulate_request(name)
                time.sleep(min(lat, 3000) / 1000)
                if status >= 400:
                    return self._send(status, {"error": "Algo salió mal", "trace_id": uuid.uuid4().hex[:16]})
                return self._send(status, {"ok": True, "endpoint": name, "latency_ms": round(lat)})
            # ------------------------------------------------ observabilidad
            if p == "/metrics" and method == "GET":
                with sim.lock:
                    return self._send(200, sim.snapshot())
            if p == "/metrics/history" and method == "GET":
                minutes = min(360, max(1, self._int_param(q, "minutes", 30)))
                with sim.lock:
                    cutoff = now().timestamp() - minutes * 60
                    rows = [{k: v for k, v in h.items() if k != "ts_obj"} for h in sim.history
                            if h["ts_obj"].timestamp() >= cutoff]
                return self._send(200, {"interval_s": 10, "points": rows})
            if p == "/logs" and method == "GET":
                return self._send(200, self._logs(q))
            if p == "/dependencies" and method == "GET":
                with sim.lock:
                    return self._send(200, {k: {"status": v, "checked_at": now().isoformat(timespec="seconds"),
                                                "check": "tcp-ping"} for k, v in sim.deps.items()})
            if p == "/changes" and method == "GET":
                with sim.lock:
                    rows = [c for c in sim.changes if not q.get("since") or c["time"] >= q["since"]]
                    return self._send(200, {"changes": rows})
            if p == "/calendar" and method == "GET":
                with sim.lock:
                    return self._send(200, {"scheduled": sim.calendar})
            # ------------------------------------------------ ITSM
            if p == "/itsm/incidents":
                if method == "GET":
                    return self._send(200, {"incidents": sim.incidents})
                return self._create_incident(self._body())
            m = re.fullmatch(r"/itsm/incidents/(INC-SIM-\d+)(/update)?", p)
            if m:
                inc = next((i for i in sim.incidents if i["id"] == m.group(1)), None)
                if not inc:
                    return self._send(404, {"error": "incident not found"})
                if method == "GET":
                    return self._send(200, inc)
                if m.group(2):
                    return self._update_incident(inc, self._body())
            return self._send(404, {"error": "not found"})
        except BadRequest as e:
            return self._send(400, {"error": "bad request", "detail": str(e)})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": "simulator error", "detail": str(e)})

    @staticmethod
    def _ts_param(q: dict, name: str):
        """Fecha ISO 8601 de un parámetro. Acepta el '+' de la zona horaria aunque llegue sin codificar."""
        raw = q.get(name)
        if not raw:
            return None
        try:
            ts = datetime.fromisoformat(raw.strip().replace(" ", "+") if "T" in raw else raw.strip())
        except ValueError:
            raise BadRequest(f"parámetro '{name}' inválido: use ISO 8601, p. ej. 2026-10-20T14:05:00+00:00")
        return ts if ts.tzinfo else ts.astimezone()

    @staticmethod
    def _int_param(q: dict, name: str, default: int) -> int:
        try:
            return int(q.get(name, default))
        except ValueError:
            raise BadRequest(f"parámetro '{name}' debe ser un entero")

    def _logs(self, q: dict) -> dict:
        sim = self.sim
        level = q.get("level", "DEBUG").upper()
        if level not in LEVELS:
            raise BadRequest(f"parámetro 'level' inválido: use {', '.join(LEVELS)}")
        min_level = LEVELS[level]
        limit = min(2000, max(1, self._int_param(q, "limit", 200)))
        since, until = self._ts_param(q, "since"), self._ts_param(q, "until")
        with sim.lock:
            rows = [e for e in sim.logs
                    if LEVELS[e["level"]] >= min_level
                    and (not q.get("source") or e["source"] == q["source"])
                    and (not since or e["ts"] >= since) and (not until or e["ts"] <= until)
                    and (not q.get("q") or q["q"].lower() in e["line"].lower())]
        return {"count": len(rows), "truncated": len(rows) > limit,
                "lines": [e["line"] for e in rows[-limit:]]}

    def _create_incident(self, b: dict):
        sim = self.sim
        missing = [k for k in ("title", "severity", "summary") if not b.get(k)]
        if b.get("__invalid__"):
            return self._send(400, {"error": "invalid JSON"})
        if missing or b.get("severity") not in SEVERITIES:
            return self._send(400, {"error": "invalid incident", "missing": missing,
                                    "severity_allowed": SEVERITIES})
        with sim.lock:
            inc = {"id": f"INC-SIM-{len(sim.incidents) + 1:04d}", "status": "OPEN",
                   "created_at": now().isoformat(timespec="seconds"), **{k: v for k, v in b.items() if k != "id"},
                   "updates": []}
            sim.incidents.append(inc)
        return self._send(201, inc)

    def _update_incident(self, inc: dict, b: dict):
        if b.get("status") and b["status"] not in ("OPEN", "MITIGATED", "RESOLVED"):
            return self._send(400, {"error": "status must be OPEN, MITIGATED or RESOLVED"})
        if b.get("severity") and b["severity"] not in SEVERITIES:
            return self._send(400, {"error": "invalid severity", "severity_allowed": SEVERITIES})
        with self.sim.lock:
            for k in ("status", "severity"):
                if b.get(k):
                    inc[k] = b[k]
            inc["updates"].append({"time": now().isoformat(timespec="seconds"), **b})
        return self._send(200, inc)

def start_tick_loop(sim: Sim) -> threading.Thread:
    """Avanza la simulación una vez por segundo en un hilo de fondo."""
    def loop():
        while True:
            try:
                sim.tick()
            except Exception as e:  # noqa: BLE001
                print("tick error:", e, flush=True)
            time.sleep(1)

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Simulador de orders-api (Reto 2)")
    ap.add_argument("--host", default=os.environ.get("SIM_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("SIM_PORT", "8080")))
    ap.add_argument("--speed", type=float, default=float(os.environ.get("SIM_SPEED", "1")),
                    help="factor de aceleración de los escenarios (1 = tiempo real)")
    ap.add_argument("--scenario", help="archivo de escenario a cargar al iniciar")
    ap.add_argument("--delay", type=float, default=0, help="segundos reales antes de que empiece el escenario")
    ap.add_argument("--seed", type=int, default=None)
    return ap


def main():
    args = build_arg_parser().parse_args()
    sim = Sim(args.speed, args.seed)
    if args.scenario:
        sim.load_scenario(json.loads(Path(args.scenario).read_text(encoding="utf-8")), args.delay)
    Handler.sim = sim
    start_tick_loop(sim)
    print(f"orders-api simulado en http://{args.host}:{args.port}  (speed={args.speed})", flush=True)
    if args.scenario:
        print(f"Escenario: {Path(args.scenario).name}, empieza en {args.delay:.0f} s", flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
