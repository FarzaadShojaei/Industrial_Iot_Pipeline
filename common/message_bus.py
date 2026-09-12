"""
Message bus abstraction.

SOLID notes
-----------
* Dependency Inversion: services depend on the `MessageBus` interface,
  never on a concrete broker. Swapping RabbitMQ for Kafka touches one file.
* Open/Closed: add `KafkaBus` without modifying any consumer code.

`InMemoryBus` lets the whole pipeline run in a single process (demo/tests).
`RabbitMQBus` is used by docker-compose for a real multi-container deployment.
"""

from __future__ import annotations

import queue
import threading
from abc import ABC, abstractmethod
from typing import Callable

Handler = Callable[[str], None]

TOPIC_READINGS = "process.readings"
TOPIC_COMMANDS = "process.commands"


class MessageBus(ABC):
    @abstractmethod
    def publish(self, topic: str, payload: str) -> None: ...

    @abstractmethod
    def subscribe(self, topic: str, handler: Handler) -> None: ...


class InMemoryBus(MessageBus):
    """Thread-safe pub/sub for single-process demos and unit tests."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = {}
        self._q: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self._lock = threading.Lock()
        threading.Thread(target=self._dispatch_loop, daemon=True).start()

    def publish(self, topic: str, payload: str) -> None:
        self._q.put((topic, payload))

    def subscribe(self, topic: str, handler: Handler) -> None:
        with self._lock:
            self._handlers.setdefault(topic, []).append(handler)

    def _dispatch_loop(self) -> None:
        while True:
            topic, payload = self._q.get()
            with self._lock:
                handlers = list(self._handlers.get(topic, []))
            for h in handlers:
                try:
                    h(payload)
                except Exception as exc:  # never let one consumer kill the bus
                    print(f"[bus] handler error on {topic}: {exc}")


class RabbitMQBus(MessageBus):
    """AMQP implementation (used in docker-compose). Requires `pika`."""

    def __init__(self, url: str = "amqp://guest:guest@rabbitmq:5672/") -> None:
        import pika  # imported lazily so the demo has no hard dependency

        self._pika = pika
        self._params = pika.URLParameters(url)
        self._pub_conn = pika.BlockingConnection(self._params)
        self._pub_ch = self._pub_conn.channel()

    def publish(self, topic: str, payload: str) -> None:
        self._pub_ch.exchange_declare(exchange=topic, exchange_type="fanout")
        self._pub_ch.basic_publish(exchange=topic, routing_key="", body=payload)

    def subscribe(self, topic: str, handler: Handler) -> None:
        def _consume() -> None:
            conn = self._pika.BlockingConnection(self._params)
            ch = conn.channel()
            ch.exchange_declare(exchange=topic, exchange_type="fanout")
            q = ch.queue_declare(queue="", exclusive=True).method.queue
            ch.queue_bind(exchange=topic, queue=q)
            ch.basic_consume(
                queue=q,
                on_message_callback=lambda c, m, p, body: handler(body.decode()),
                auto_ack=True,
            )
            ch.start_consuming()

        import threading

        threading.Thread(target=_consume, daemon=True).start()
