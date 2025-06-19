"""Utilities to simulate IoT fire monitoring nodes and visualize readings."""

import json
import math
import random
import time
from typing import Callable, List, Optional

import requests
import folium
from folium.plugins import HeatMap, PolyLineTextPath
import branca.colormap as cm

try:
    from kafka import KafkaProducer
except Exception:  # pragma: no cover - kafka is optional
    KafkaProducer = None

# ---------------------------------------------------------------------------
# Weather helpers
# ---------------------------------------------------------------------------

def get_current_weather(latitude: float, longitude: float):
    """Return (temperature, humidity) from the Open-Meteo API."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current_weather": True,
        "hourly": "relative_humidity_2m",
        "timezone": "UTC",
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        temp = data.get("current_weather", {}).get("temperature")
        humidity = None
        hourly = data.get("hourly", {})
        if hourly.get("relative_humidity_2m"):
            humidity = hourly["relative_humidity_2m"][0]
        return temp, humidity
    except Exception:
        return None, None

# ---------------------------------------------------------------------------
# Node simulation
# ---------------------------------------------------------------------------

class IoTNode:
    """Represents a single simulated IoT node."""

    DIRECTIONS = {
        "N": 0,
        "NE": 45,
        "E": 90,
        "SE": 135,
        "S": 180,
        "SW": 225,
        "W": 270,
        "NW": 315,
    }

    def __init__(self, node_id: str, latitude: float, longitude: float, wind_direction: str = "N"):
        self.node_id = node_id
        self.latitude = latitude
        self.longitude = longitude

        temp, hum = get_current_weather(latitude, longitude)
        self.temperature = temp if temp is not None else random.uniform(15, 25)
        self.humidity = hum if hum is not None else random.uniform(30, 50)

        self.wind_vector = (
            random.uniform(0, 10),
            self.DIRECTIONS.get(wind_direction.upper(), 0),
        )

    def generate_data(self):
        """Generate a new sensor reading with noise."""
        self.temperature += random.uniform(-0.5, 0.5)
        self.wind_vector = (
            max(0, self.wind_vector[0] + random.uniform(-1, 1)),
            (self.wind_vector[1] + random.uniform(-10, 10)) % 360,
        )
        self.humidity += random.uniform(-1, 1)
        return {
            "node_id": self.node_id,
            "gps": [self.latitude, self.longitude],
            "temperature": round(self.temperature, 2),
            "wind_vector": [round(self.wind_vector[0], 2), round(self.wind_vector[1], 2)],
            "humidity": round(self.humidity, 2),
        }


def initialize_nodes_center_grid(
    grid_size: int,
    center_lat: float,
    center_long: float,
    lat_spread: float = 0.01,
    lon_spread: float = 0.01,
    wind_direction: str = "N",
) -> List[IoTNode]:
    """Create a grid of nodes evenly spaced around a center coordinate."""
    nodes = []
    lat_start = center_lat - lat_spread
    lon_start = center_long - lon_spread
    lat_step = (2 * lat_spread) / max(grid_size - 1, 1)
    lon_step = (2 * lon_spread) / max(grid_size - 1, 1)
    for i in range(grid_size):
        for j in range(grid_size):
            latitude = lat_start + i * lat_step
            longitude = lon_start + j * lon_step
            node_id = f"node_{i+1}_{j+1}"
            nodes.append(IoTNode(node_id, latitude, longitude, wind_direction))
    return nodes

# ---------------------------------------------------------------------------
# Visualization helpers
# ---------------------------------------------------------------------------

def visualize_nodes_folium(nodes: List[IoTNode]):
    """Display node markers on a folium map."""
    first = nodes[0]
    m = folium.Map(location=[first.latitude, first.longitude], zoom_start=14)
    for n in nodes:
        folium.Marker([n.latitude, n.longitude], popup=n.node_id).add_to(m)
    return m


def visualize_temperature_heatmap(nodes: List[IoTNode], zoom_start: int = 14):
    """Render a smooth temperature heatmap."""
    first = nodes[0]
    m = folium.Map(location=[first.latitude, first.longitude], zoom_start=zoom_start)
    temps = [n.temperature for n in nodes]
    tmin, tmax = min(temps), max(temps)
    heat_data = [
        [n.latitude, n.longitude, (n.temperature - tmin) / (tmax - tmin or 1)]
        for n in nodes
    ]
    HeatMap(
        heat_data,
        min_opacity=0.3,
        radius=50,
        blur=35,
        max_zoom=zoom_start,
        gradient={0.2: "blue", 0.4: "cyan", 0.6: "lime", 0.8: "yellow", 1.0: "red"},
    ).add_to(m)
    for n in nodes:
        folium.Marker([n.latitude, n.longitude], popup=n.node_id).add_to(m)
    return m


def visualize_wind_vectors(nodes: List[IoTNode], scale: float = 0.005):
    """Draw wind direction arrows for each node."""
    first = nodes[0]
    m = folium.Map(location=[first.latitude, first.longitude], zoom_start=14)
    for n in nodes:
        folium.Marker([n.latitude, n.longitude], popup=n.node_id).add_to(m)
        speed, direction = n.wind_vector
        end_lat = n.latitude + scale * speed * math.cos(math.radians(direction))
        end_lon = n.longitude + scale * speed * math.sin(math.radians(direction))
        line = folium.PolyLine([[n.latitude, n.longitude], [end_lat, end_lon]], color="blue", weight=2).add_to(m)
        PolyLineTextPath(line, "→", repeat=True, offset=5, attributes={"fill": "blue", "font-weight": "bold"}).add_to(m)
    return m


def visualize_metric_folium(
    nodes: List[IoTNode],
    metric: str,
    accessor: Optional[Callable[[IoTNode], float]] = None,
):
    """Color nodes by ``metric`` using a linear colormap."""
    first = nodes[0]
    m = folium.Map(location=[first.latitude, first.longitude], zoom_start=14)
    values = [accessor(n) if accessor else getattr(n, metric) for n in nodes]
    colormap = cm.linear.YlOrRd_09.scale(min(values), max(values))
    for n in nodes:
        val = accessor(n) if accessor else getattr(n, metric)
        folium.CircleMarker(
            [n.latitude, n.longitude],
            radius=6,
            color=colormap(val),
            fill=True,
            fill_color=colormap(val),
            popup=f"{n.node_id} {metric}: {val:.2f}",
        ).add_to(m)
    colormap.caption = metric.capitalize()
    colormap.add_to(m)
    return m

# ---------------------------------------------------------------------------
# Kafka streaming
# ---------------------------------------------------------------------------

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


if __name__ == "__main__":
    nodes = initialize_nodes_center_grid(
        grid_size=5,
        center_lat=34.0522,
        center_long=-118.2437,
        lat_spread=0.02,
        lon_spread=0.02,
        wind_direction="NE",
    )

    visualize_nodes_folium(nodes).save("iot_nodes_map.html")
    visualize_temperature_heatmap(nodes).save("iot_temperature_heatmap.html")
    visualize_metric_folium(nodes, "humidity").save("iot_humidity_map.html")
    visualize_wind_vectors(nodes).save("iot_wind_vector_map.html")
    # Uncomment to stream data
    # stream_data(nodes, topic="iot_fire_data", interval=2)
