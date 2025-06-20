"""Kafka streaming utilities."""
from __future__ import annotations
import json
import time
from typing import List, Optional, Callable, Any
from kafka.errors import NoBrokersAvailable

try:
    from kafka import KafkaProducer
except Exception:  # pragma: no cover - kafka is optional
    KafkaProducer = None

print("KafkaProducer is", KafkaProducer)

from .nodes import IoTNode

__all__ = [
    "stream_data",
    "get_producer",
    "DummyProducer",
]


class DummyProducer:
    """Fallback producer used when Kafka is unavailable."""

    def __init__(self, value_serializer: Optional[Callable[[Any], Any]] = None) -> None:
        self.value_serializer = value_serializer or (lambda v: v)
        self.sent_messages: list[tuple[str, Any]] = []

    def send(self, topic: str, value: dict):
        encoded = self.value_serializer(value)
        self.sent_messages.append((topic, encoded))
        print(f"[DummyProducer] {topic}: {encoded}")


def get_producer():
    if KafkaProducer is None:
        return DummyProducer(value_serializer=lambda v: json.dumps(v).encode("utf-8"))
    try:
        return KafkaProducer(
            bootstrap_servers=["localhost:9092"],
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )
    except NoBrokersAvailable:
        return DummyProducer(value_serializer=lambda v: json.dumps(v).encode("utf-8"))


def stream_data(
    nodes: List[IoTNode],
    topic: str,
    interval: int = 1,
    *,
    iterations: Optional[int] = None,
    producer: Optional[Any] = None,
) -> None:
    """Send sensor data to a Kafka topic or a dummy producer.
    Parameters
    ----------
    nodes:
        List of IoT nodes to generate data from.
    topic:
        Topic name to send data to.
    interval:
        Delay between iterations in seconds.
    iterations:
        Number of iterations to run. ``None`` runs indefinitely.
    producer:
        Optional producer instance. If ``None`` a producer is created via
        :func:`get_producer`.
    """

    producer = producer or get_producer()
    count = 0
    while True:
        for node in nodes:
            data = node.generate_data()
            producer.send(topic, value=data)
            print(f"Sent: {data}")
        count += 1
        if iterations is not None and count >= iterations:
            break
        time.sleep(interval)

