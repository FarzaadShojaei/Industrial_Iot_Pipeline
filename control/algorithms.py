"""
Process-control algorithms — Strategy pattern.

The control service is closed for modification, open for extension:
new algorithms (fuzzy, MPC, ML-based...) are added as new strategies
without touching the service. This is the Open/Closed principle plus
Liskov substitution (any `ControlAlgorithm` is interchangeable).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from common.models import SensorReading


class ControlAlgorithm(ABC):
    """Given the latest reading, return the pump speed setpoint in %."""

    @abstractmethod
    def compute(self, reading: SensorReading) -> float: ...


class HysteresisControl(ControlAlgorithm):
    """Bang-bang with a deadband — the classic PLC-style level control."""

    def __init__(self, low: float = 45.0, high: float = 55.0,
                 pump_on: float = 80.0, pump_off: float = 10.0) -> None:
        self._low, self._high = low, high
        self._on_speed, self._off_speed = pump_on, pump_off
        self._output = pump_off

    def compute(self, reading: SensorReading) -> float:
        if reading.level_pct > self._high:
            self._output = self._on_speed
        elif reading.level_pct < self._low:
            self._output = self._off_speed
        return self._output


class PIDControl(ControlAlgorithm):
    """Textbook PI(D) keeping the tank at `setpoint` % level."""

    def __init__(self, setpoint: float = 50.0,
                 kp: float = 4.0, ki: float = 0.8, kd: float = 0.0) -> None:
        self.setpoint = setpoint
        self._kp, self._ki, self._kd = kp, ki, kd
        self._integral = 0.0
        self._prev_err: float | None = None
        self._prev_t: float | None = None

    def compute(self, reading: SensorReading) -> float:
        now = time.time()
        # NOTE: error sign — level above setpoint means pump MORE
        err = reading.level_pct - self.setpoint
        dt = (now - self._prev_t) if self._prev_t else 0.0

        p = self._kp * err
        if dt > 0:
            self._integral += err * dt
            self._integral = max(-100.0, min(100.0, self._integral))  # anti-windup
        i = self._ki * self._integral
        d = self._kd * ((err - self._prev_err) / dt) if (dt > 0 and self._prev_err is not None) else 0.0

        self._prev_err, self._prev_t = err, now
        return max(0.0, min(100.0, 50.0 + p + i + d))  # 50 % ≈ flow-balance point
