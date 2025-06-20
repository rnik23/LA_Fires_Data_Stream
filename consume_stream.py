#!/usr/bin/env python3
# consume_stream.py

from kafka import KafkaConsumer
import json

def main():
    # 1. Connect and subscribe
    consumer = KafkaConsumer(
        "iot_fire_data",
        bootstrap_servers=["localhost:9092"],
        auto_offset_reset="earliest",      # start from the beginning
        consumer_timeout_ms=5000,          # stop after 5 s of no new messages
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
    )

    print("Listening for iot_fire_data…")
    for msg in consumer:
        print(msg.value)

if __name__ == "__main__":
    main()