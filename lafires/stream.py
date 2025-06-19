"""Kafka streaming utilities."""
from __future__ import annotations

import json
import time
from typing import List

try:
    from kafka import KafkaProducer
except Exception:  # pragma: no cover - kafka is optional
    KafkaProducer = None

from .nodes import IoTNode

__all__ = [
    "stream_data",
    "get_producer",
    "DummyProducer",
]


class DummyProducer:
    """Fallback producer used when Kafka is unavailable."""

    def send(self, topic: str, value: dict):
        print(f"[DummyProducer] {topic}: {value}")


def get_producer():
    if KafkaProducer is None:
        return DummyProducer()
    return KafkaProducer(
        bootstrap_servers=["localhost:9092"],
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )


def stream_data(nodes: List[IoTNode], topic: str, interval: int = 1):
    """Continuously send sensor data to Kafka."""
    producer = get_producer()
    while True:
        for node in nodes:
            data = node.generate_data()
            producer.send(topic, value=data)
            print(f"Sent: {data}")
        time.sleep(interval)

