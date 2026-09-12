"""
Control service
===============
Subscribes to `process.readings`, runs the injected control strategy,
publishes `process.commands`. It never touches Modbus directly —
that's the connector's job (Single Responsibility).
"""

from __future__ import annotations

import logging

from common.message_bus import TOPIC_COMMANDS, TOPIC_READINGS, MessageBus
from common.models import ActuatorCommand, SensorReading
from control.algorithms import ControlAlgorithm

log = logging.getLogger("control")


class ControlService:
    def __init__(self, bus: MessageBus, algorithm: ControlAlgorithm) -> None:
        self._bus = bus
        self._algorithm = algorithm          # injected — Strategy + DIP
        bus.subscribe(TOPIC_READINGS, self._on_reading)

    def _on_reading(self, payload: str) -> None:
        reading = SensorReading.from_json(payload)
        speed = self._algorithm.compute(reading)
        cmd = ActuatorCommand(target=reading.source, pump_speed_pct=speed)
        self._bus.publish(TOPIC_COMMANDS, cmd.to_json())
        log.debug("level=%.1f%% -> pump=%.1f%%", reading.level_pct, speed)
