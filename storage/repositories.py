"""
Storage service — Repository pattern.

The service persists every reading through a `ReadingRepository` interface.
* `SQLiteRepository`  — zero-dependency demo / relational (SQL requirement)
* `InfluxRepository`  — time-series store used in docker-compose (NoSQL requirement)

Interface Segregation: the repository exposes only what consumers need
(save + recent), not a leaky generic CRUD surface.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from abc import ABC, abstractmethod

from common.message_bus import TOPIC_READINGS, MessageBus
from common.models import SensorReading

log = logging.getLogger("storage")


class ReadingRepository(ABC):
    @abstractmethod
    def save(self, reading: SensorReading) -> None: ...

    @abstractmethod
    def recent(self, limit: int = 10) -> list[SensorReading]: ...


class SQLiteRepository(ReadingRepository):
    def __init__(self, path: str = "readings.db") -> None:
        self._path = path
        self._lock = threading.Lock()
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS readings (
                       ts REAL, source TEXT, level_pct REAL, inflow_lpm REAL,
                       temperature_c REAL, pump_speed_pct REAL,
                       valve_open INTEGER, alarm_high_level INTEGER)"""
            )

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def save(self, reading: SensorReading) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO readings VALUES (?,?,?,?,?,?,?,?)",
                (reading.ts, reading.source, reading.level_pct,
                 reading.inflow_lpm, reading.temperature_c,
                 reading.pump_speed_pct, int(reading.valve_open),
                 int(reading.alarm_high_level)),
            )

    def recent(self, limit: int = 10) -> list[SensorReading]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT ts, source, level_pct, inflow_lpm, temperature_c,"
                " pump_speed_pct, valve_open, alarm_high_level"
                " FROM readings ORDER BY ts DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            SensorReading(source=r[1], level_pct=r[2], inflow_lpm=r[3],
                          temperature_c=r[4], pump_speed_pct=r[5],
                          valve_open=bool(r[6]), alarm_high_level=bool(r[7]),
                          ts=r[0])
            for r in rows
        ]


class InfluxRepository(ReadingRepository):
    """Time-series backend for the docker-compose deployment (influxdb-client)."""

    def __init__(self, url: str, token: str, org: str, bucket: str) -> None:
        from influxdb_client import InfluxDBClient, Point  # lazy import

        self._Point = Point
        self._bucket, self._org = bucket, org
        self._client = InfluxDBClient(url=url, token=token, org=org)
        self._write = self._client.write_api()

    def save(self, reading: SensorReading) -> None:
        p = (self._Point("tank")
             .tag("source", reading.source)
             .field("level_pct", reading.level_pct)
             .field("inflow_lpm", reading.inflow_lpm)
             .field("temperature_c", reading.temperature_c)
             .field("pump_speed_pct", reading.pump_speed_pct)
             .field("alarm", int(reading.alarm_high_level)))
        self._write.write(bucket=self._bucket, org=self._org, record=p)

    def recent(self, limit: int = 10) -> list[SensorReading]:
        raise NotImplementedError("query via Flux / Grafana dashboard")


class StorageService:
    def __init__(self, bus: MessageBus, repo: ReadingRepository) -> None:
        self._repo = repo
        bus.subscribe(TOPIC_READINGS, self._on_reading)

    def _on_reading(self, payload: str) -> None:
        self._repo.save(SensorReading.from_json(payload))
