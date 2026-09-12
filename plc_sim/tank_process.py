"""
PLC Simulator — Tank Level Process
==================================
Simulates an industrial tank (fill/drain) and exposes its I/O over
Modbus TCP, exactly like a Siemens/Schneider PLC or an OpenPLC runtime would.

Register map (holding registers, 16-bit):
    HR0  tank level        (0-1000  -> 0.0-100.0 %)
    HR1  inlet flow rate   (0-1000  -> 0.0-100.0 L/min)
    HR2  temperature       (x10     -> e.g. 253 = 25.3 °C)
    HR3  pump speed SP     (0-1000  -> 0.0-100.0 %)  [written by control svc]

Coils:
    C0   inlet valve open
    C1   high-level alarm (level > 90 %)

Any Modbus TCP client (our connector, but also Codesys, Ignition, Node-RED)
can talk to this simulator on port 5020.
"""

import asyncio
import logging
import math
import random
import time

from pymodbus.datastore import (
    ModbusSlaveContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.server import StartAsyncTcpServer

log = logging.getLogger("plc_sim")

# --- Register addresses (single source of truth, imported by services) ---
HR_LEVEL = 0
HR_INFLOW = 1
HR_TEMP = 2
HR_PUMP_SP = 3
CO_VALVE = 0
CO_ALARM = 1

MODBUS_PORT = 5020


class TankPhysics:
    """Very small first-order model of a tank with inlet valve and drain pump."""

    def __init__(self) -> None:
        self.level = 30.0          # %
        self.inflow = 60.0         # L/min when valve open
        self.temperature = 25.0    # °C
        self.t0 = time.time()

    def step(self, dt: float, valve_open: bool, pump_speed_pct: float) -> None:
        inflow = self.inflow if valve_open else 0.0
        # inlet flow wanders a bit like a real process
        self.inflow = max(30.0, min(90.0, self.inflow + random.uniform(-2, 2)))
        outflow = 0.9 * pump_speed_pct  # pump capacity ~90 L/min at 100 %
        self.level += (inflow - outflow) * dt * 0.05
        self.level = max(0.0, min(100.0, self.level))
        # slow ambient temperature oscillation + noise
        self.temperature = 25.0 + 3.0 * math.sin((time.time() - self.t0) / 60.0) \
            + random.uniform(-0.2, 0.2)


async def run_simulator(port: int = MODBUS_PORT) -> None:
    device = ModbusSlaveContext(
        hr=ModbusSequentialDataBlock(0, [0] * 16),
        co=ModbusSequentialDataBlock(0, [0] * 16),
        di=ModbusSequentialDataBlock(0, [0] * 16),
        ir=ModbusSequentialDataBlock(0, [0] * 16),
    )
    context = ModbusServerContext(slaves=device, single=True)
    physics = TankPhysics()

    # start with the valve open so the tank fills
    device.setValues(1, CO_VALVE, [1])  # fc 1 = coils

    async def process_loop() -> None:
        dt = 0.25
        while True:
            valve_open = bool(device.getValues(1, CO_VALVE, count=1)[0])
            pump_sp = device.getValues(3, HR_PUMP_SP, count=1)[0] / 10.0  # fc 3 = HR
            physics.step(dt, valve_open, pump_sp)

            device.setValues(3, HR_LEVEL, [int(physics.level * 10)])
            device.setValues(3, HR_INFLOW, [int(physics.inflow * 10)])
            device.setValues(3, HR_TEMP, [int(physics.temperature * 10)])
            device.setValues(1, CO_ALARM, [1 if physics.level > 90.0 else 0])
            await asyncio.sleep(dt)

    asyncio.create_task(process_loop())
    log.info("PLC simulator listening on Modbus TCP :%s", port)
    await StartAsyncTcpServer(context=context, address=("0.0.0.0", port))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_simulator())
