#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Ghost‑Watch con notificaciones de Termux
- Chequea la URL cada 15 min.
- Muestra tabla coloreada (Rich).
- Guarda log JSON.
- Envía notificación CLI cuando cambia el estado (up ↔ down).
"""

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

import requests
import schedule
from rich import box
from rich.console import Console
from rich.table import Table

# ---------------------- CONFIGURACIÓN ----------------------
URL          = "https://ejemplo.com"   # ← pon tu URL aquí
INTERVAL_MIN = 15                      # minutos entre checks
TIMEOUT       = 10                     # s, tiempo máximo de espera
LOG_FILE      = Path("ghost_watch_log.json")
console       = Console()
# -----------------------------------------------------------

def load_log() -> list:
    if LOG_FILE.exists():
        try:
            return json.loads(LOG_FILE.read_text())
        except json.JSONDecodeError:
            return []
    return []

def save_log(events: list) -> None:
    LOG_FILE.write_text(json.dumps(events, indent=2, ensure_ascii=False))

def log_event(kind: str, payload: dict) -> None:
    entry = {"timestamp": datetime.utcnow().isoformat()+"Z", "type": kind, **payload}
    events = load_log()
    events.append(entry)
    save_log(events)

def termux_notify(title: str, text: str, priority: int = 0) -> None:
    """
    Lanza una notificación en Termux.
    priority = -2 (baja) … 2 (alta). 0 = normal.
    """
    subprocess.run([
        "termux-notification",
        f"--title={title}",
        f"--content={text}",
        f"--priority={priority}"
    ], check=False)

def check_url() -> dict:
    start = time.monotonic()
    try:
        resp = requests.get(URL, timeout=TIMEOUT, verify=False)
        elapsed = (time.monotonic() - start) * 1000          # ms
        up = 200 <= resp.status_code < 400
        status = resp.status_code
        err = None
    except Exception as e:
        elapsed = None
        status = None
        up = False
        err = str(e)
    return {"up": up, "status": status,
            "response_ms": round(elapsed, 1) if elapsed else None,
            "error": err}

# ----------- Estado para detección de caídas ----------------
last_state = {"up": None, "since": None}

def monitor_job() -> None:
    global last_state
    now = datetime.utcnow()
    res = check_url()

    # ----------- Detección de cambio de estado ----------------
    if last_state["up"] is None:                     # primer run
        last_state = {"up": res["up"], "since": now}
        log_event("startup", {"url": URL, "up": res["up"],
                              "response_ms": res["response_ms"]})
    elif res["up"] != last_state["up"]:               # cambio detectado
        downtime = (now - last_state["since"]).total_seconds()
        if res["up"]:                                 # ↓ → ↑ (recuperación)
            log_event("recovery", {"url": URL,
                                   "downtime_s": int(downtime)})
            termux_notify("✅ Ghost‑Watch", f"✅ {URL} está de nuevo ONLINE",
                          priority=1)
        else:                                         # ↑ → ↓ (caída)
            log_event("down", {"url": URL,
                               "uptime_s": int(downtime)})
            termux_notify("⚠️ Ghost‑Watch", f"❌ {URL} ha caído",
                          priority=2)
        last_state = {"up": res["up"], "since": now}
    else:
        # sin cambio → opcional registro de latido
        log_event("heartbeat", {"url": URL, "up": res["up"],
                                "response_ms": res["response_ms"]})

    # -------------------- UI en consola ------------------------
    tbl = Table(title="🕸️ Ghost‑Watch", box=box.SIMPLE_HEAVY)
    tbl.add_column("UTC", style="dim")
    tbl.add_column("URL")
    tbl.add_column("Estado", justify="center")
    tbl.add_column("Código")
    tbl.add_column("RT (ms)", justify="right")
    tbl.add_column("Detalle")

    estado = "[green]UP[/green]" if res["up"] else "[red]DOWN[/red]"
    codigo = str(res["status"]) if res["status"] else "-"
    rt     = str(res["response_ms"]) if res["response_ms"] else "-"
    detalle= res["error"] if res["error"] else "-"

    tbl.add_row(now.strftime("%Y-%m-%d %H:%M:%S"),
                URL, estado, codigo, rt, detalle)

    console.clear()
    console.print(tbl)

# ------------------------- MAIN -----------------------------
def main() -> None:
    console.print("[bold]Ghost‑Watch con notificaciones iniciada[/bold] – URL:", URL)
    schedule.every(INTERVAL_MIN).minutes.do(monitor_job)
    monitor_job()                # ejecución inmediata al lanzar
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[italic]Detenido por el usuario[/italic]")
