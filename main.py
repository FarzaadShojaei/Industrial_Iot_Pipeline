"""
Run the full pipeline locally, no Docker needed:

    PLC sim (Modbus TCP :5020)
        -> ModbusConnector  -> [process.readings] -> ControlService
                                        |                  |
                                        v                  v
                                 StorageService     [process.commands]
                                 (SQLite)                  |
                                        <- write pump SP <-+

Usage:
    python main.py                # PID control (default)
    python main.py --hysteresis   # bang-bang control
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import threading
import time

from common.message_bus import InMemoryBus
from connector.modbus_connector import ModbusConnector
from control.algorithms import HysteresisControl, PIDControl
from control.control_service import ControlService
from plc_sim.tank_process import run_simulator
from storage.repositories import SQLiteRepository, StorageService

logging.basicConfig(level=logging.INFO, format="%(name)-10s %(message)s")
log = logging.getLogger("main")


def start_plc_sim() -> None:
    threading.Thread(
        target=lambda: asyncio.run(run_simulator()), daemon=True
    ).start()
    time.sleep(1.5)  # give the Modbus server time to bind


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hysteresis", action="store_true")
    parser.add_argument("--seconds", type=int, default=20)
    args = parser.parse_args()

    start_plc_sim()

    bus = InMemoryBus()
    repo = SQLiteRepository("readings.db")
    StorageService(bus, repo)

    algorithm = HysteresisControl() if args.hysteresis else PIDControl(setpoint=50.0)
    ControlService(bus, algorithm)
    log.info("control strategy: %s", type(algorithm).__name__)

    connector = ModbusConnector(bus)
    threading.Thread(target=connector.run_forever, daemon=True).start()

    # live console "HMI"
    t_end = time.time() + args.seconds
    while time.time() < t_end:
        time.sleep(2)
        latest = repo.recent(limit=1)
        if latest:
            r = latest[0]
            bar = "#" * int(r.level_pct / 2)
            log.info("level %5.1f%% |%-50s| pump %5.1f%%  T %.1f°C%s",
                     r.level_pct, bar, r.pump_speed_pct, r.temperature_c,
                     "  *ALARM*" if r.alarm_high_level else "")

    rows = repo.recent(limit=5)
    log.info("--- last 5 rows persisted in SQLite ---")
    for r in rows:
        log.info("%s  level=%.1f%%  pump=%.1f%%", 
                 time.strftime("%H:%M:%S", time.localtime(r.ts)),
                 r.level_pct, r.pump_speed_pct)


if __name__ == "__main__":
    main()
