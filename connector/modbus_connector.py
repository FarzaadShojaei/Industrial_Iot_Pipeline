"""
Connector service
=================
The "data connector & transformer" from the job description:

    3rd-party device (Modbus TCP)  ->  raw registers
                                   ->  scaling / engineering units
                                   ->  validated JSON on the message bus

SOLID notes
-----------
* Single Responsibility: this service only acquires + transforms data.
  It knows nothing about control logic or storage.
* Dependency Inversion: receives a `MessageBus`, not a broker.
"""

from __future__ import annotations

import logging
import time

from pymodbus.client import ModbusTcpClient

from common.message_bus import TOPIC_COMMANDS, TOPIC_READINGS, MessageBus
from common.models import ActuatorCommand, SensorReading
from plc_sim.tank_process import (
    CO_ALARM,
    CO_VALVE,
    HR_INFLOW,
    HR_LEVEL,
    HR_PUMP_SP,
    HR_TEMP,
)

log = logging.getLogger("connector")


class ModbusConnector:
    def __init__(
        self,
        bus: MessageBus,
        host: str = "127.0.0.1",
        port: int = 5020,
        source_id: str = "plc-line1",
        poll_s: float = 0.5,
    ) -> None:
        self._bus = bus
        self._client = ModbusTcpClient(host, port=port)
        self._source = source_id
        self._poll_s = poll_s
        # commands coming back from the control service are written to the PLC
        bus.subscribe(TOPIC_COMMANDS, self._on_command)

    # ---------------- acquisition ----------------
    def run_forever(self) -> None:
        self._client.connect()
        log.info("connected to %s:%s", self._client.comm_params.host,
                 self._client.comm_params.port)
        while True:
            try:
                reading = self.poll_once()
                self._bus.publish(TOPIC_READINGS, reading.to_json())
            except Exception as exc:
                log.error("poll failed: %s", exc)
                time.sleep(1.0)
                self._client.connect()  # simple reconnect strategy
            time.sleep(self._poll_s)

    def poll_once(self) -> SensorReading:
        hr = self._client.read_holding_registers(HR_LEVEL, count=4)
        co = self._client.read_coils(CO_VALVE, count=2)
        if hr.isError() or co.isError():
            raise ConnectionError("modbus read error")
        return self.transform(hr.registers, co.bits)

    # ---------------- transformation ----------------
    def transform(self, registers: list[int], coils: list[bool]) -> SensorReading:
        """Raw 16-bit registers -> engineering units (pure function, unit-tested)."""
        return SensorReading(
            source=self._source,
            level_pct=registers[HR_LEVEL] / 10.0,
            inflow_lpm=registers[HR_INFLOW] / 10.0,
            temperature_c=registers[HR_TEMP] / 10.0,
            pump_speed_pct=registers[HR_PUMP_SP] / 10.0,
            valve_open=bool(coils[CO_VALVE]),
            alarm_high_level=bool(coils[CO_ALARM]),
        )

    # ---------------- write-back ----------------
    def _on_command(self, payload: str) -> None:
        cmd = ActuatorCommand.from_json(payload)
        if cmd.target != self._source:
            return
        raw = int(max(0.0, min(100.0, cmd.pump_speed_pct)) * 10)
        self._client.write_register(HR_PUMP_SP, raw)
        log.debug("pump SP -> %.1f %%", cmd.pump_speed_pct)
