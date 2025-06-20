import json

import pytest

from lafires import IoTNode, initialize_nodes_center_grid, wind_generator, DummyProducer
from lafires.stream import stream_data
from lafires import weather


def test_dummy_producer_serialization():
    prod = DummyProducer(value_serializer=json.dumps)
    prod.send("topic", {"a": 1})
    assert prod.sent_messages == [("topic", json.dumps({"a": 1}))]


def test_get_producer_returns_dummy(monkeypatch):
    import lafires.stream as stream
    monkeypatch.setattr(stream, "KafkaProducer", None)
    p = stream.get_producer()
    assert isinstance(p, stream.DummyProducer)


def test_initialize_nodes_center_grid():
    nodes = initialize_nodes_center_grid(2, 0.0, 0.0)
    assert len(nodes) == 4
    ids = {n.node_id for n in nodes}
    assert len(ids) == len(nodes)


def test_iotnode_generate_data():
    node = IoTNode("id", 0.0, 0.0, 25.0, 40.0, 5.0, 90)
    data = node.generate_data()
    required = {"node_id", "gps", "temperature", "wind_vector", "humidity"}
    assert required <= data.keys()


def test_wind_generator():
    gen = wind_generator(3.0)
    for _ in range(5):
        val = next(gen)
        assert val >= 0


def test_get_current_weather(monkeypatch):
    resp_data = {
        "current_weather": {"temperature": 20, "windspeed": 3, "winddirection": 90},
        "hourly": {"relative_humidity_2m": [50]},
    }

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return resp_data

    monkeypatch.setattr(weather.requests, "get", lambda *a, **k: Resp())
    assert weather.get_current_weather(0, 0) == (20, 50, 3, 90)


def test_stream_data_iterations(monkeypatch):
    node = IoTNode("id", 0.0, 0.0, 25.0, 40.0, 5.0, 90)
    prod = DummyProducer(value_serializer=json.dumps)
    monkeypatch.setattr(stream_data.__globals__["time"], "sleep", lambda x: None)
    stream_data([node], "topic", interval=0, iterations=2, producer=prod)
    assert len(prod.sent_messages) == 2
