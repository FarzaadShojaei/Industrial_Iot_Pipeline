"""Shared domain models — the 'contract' between microservices."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class SensorReading:
    """One engineering-units snapshot of the process, produced by the connector."""

    source: str                 # e.g. "plc-line1"
    level_pct: float
    inflow_lpm: float
    temperature_c: float
    pump_speed_pct: float
    valve_open: bool
    alarm_high_level: bool
    ts: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(raw: str) -> "SensorReading":
        return SensorReading(**json.loads(raw))


@dataclass(frozen=True)
class ActuatorCommand:
    """Command computed by the control service, written back to the PLC."""

    target: str                 # e.g. "plc-line1"
    pump_speed_pct: float
    ts: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(raw: str) -> "ActuatorCommand":
        return ActuatorCommand(**json.loads(raw))
