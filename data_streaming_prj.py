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

    def __init__(
        self,
        node_id: str,
        latitude: float,
        longitude: float,
        temperature: float,
        humidity: float,
        wind_direction: str = "N",
    ):
        self.node_id = node_id
        self.latitude = latitude
        self.longitude = longitude
        self.temperature = temperature
        self.humidity = humidity
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
    center_temp, center_hum = get_current_weather(center_lat, center_long)
    if center_temp is None:
        center_temp = random.uniform(15, 25)
    if center_hum is None:
        center_hum = random.uniform(30, 50)
    nodes = []
    lat_start = center_lat - lat_spread
    lon_start = center_long - lon_spread
    lat_step = (2 * lat_spread) / max(grid_size - 1, 1)
    lon_step = (2 * lon_spread) / max(grid_size - 1, 1)

    # typical low-cost digital temperature sensors (e.g. DHT22) have about ±2% accuracy
    noise_pct = 0.02

    for i in range(grid_size):
        for j in range(grid_size):
            latitude = lat_start + i * lat_step
            longitude = lon_start + j * lon_step
            node_id = f"node_{i+1}_{j+1}"
            temp_noise = center_temp * random.uniform(-noise_pct, noise_pct)
            hum_noise  = center_hum  * random.uniform(-noise_pct, noise_pct)
            # apply ±noise_pct variation
            temp = center_temp + temp_noise
            hum  = center_hum   + hum_noise
            nodes.append(
                IoTNode(
                    node_id,
                    latitude,
                    longitude,
                    wind_direction=wind_direction,
                    temperature = temp,
                    humidity= hum
                )
            )
    return nodes

# ---------------------------------------------------------------------------
# Visualization helpers
# ---------------------------------------------------------------------------

def visualize_nodes_folium(nodes: List[IoTNode]):
    """Display node markers on a folium map as small points."""
    first = nodes[0]
    m = folium.Map(location=[first.latitude, first.longitude], zoom_start=14)
    for n in nodes:
        folium.CircleMarker(
            [n.latitude, n.longitude],
            radius=3,
            color="black",
            fill=True,
            fill_color="black",
            fill_opacity=1,
            popup=n.node_id,
        ).add_to(m)
    return m


import statistics

import statistics

def visualize_temperature_heatmap(nodes: List[IoTNode], zoom_start: int = 14):
    """Render a heatmap that only shows red for >2σ deviations—normal noise stays in cooler colors."""
    # center map
    first = nodes[0]
    m = folium.Map(location=[first.latitude, first.longitude], zoom_start=zoom_start)

    # compute mean & σ
    temps = [n.temperature for n in nodes]
    mean_temp = statistics.mean(temps)
    std_temp = statistics.pstdev(temps) or 1

    # we’ll treat ±2σ as our “alarm” threshold
    z_threshold = 3.0
    lower, upper = -z_threshold * std_temp, z_threshold * std_temp

    heat_data = []
    for n in nodes:
        z = (n.temperature - mean_temp) / std_temp
        # clamp into ±2σ
        z_clamped = max(lower, min(upper, z))
        # normalize to [0, 1]
        norm = (z_clamped - lower) / (upper - lower)

        # if it’s within threshold, push it into the cooler half of the scale
        if abs(z) < z_threshold:
            weight = norm * 0.5     # 0.0–0.5 range → blue→cyan
        else:
            # if it’s beyond threshold, map into 0.5–1.0 range → yellow→red
            # (abs(z)-threshold)/(z_threshold) gives 0.0–1.0 for z in [±2σ…±4σ], but we already clamped to 2σ
            weight = 0.5 + (abs(z_clamped) - (z_threshold * std_temp)) / ((z_threshold * std_temp) - lower) * 0.5

        heat_data.append([n.latitude, n.longitude, weight])

    gradient = {
        0.0: "blue",    # cold outliers up to -2σ
        0.25: "cyan",  
        0.5: "lime",    # normal noise (±2σ)
        0.75: "yellow", # slight alarms
        1.0: "red",     # full alarm (>2σ)
    }

    HeatMap(
        heat_data,
        min_opacity=0.3,
        radius=50,
        blur=35,
        max_zoom=zoom_start,
        gradient=gradient,
    ).add_to(m)

    # still drop markers for context
    for n in nodes:
        folium.CircleMarker(
            [n.latitude, n.longitude],
            radius=3,
            color="black",
            fill=True,
            fill_color="black",
            fill_opacity=1,
            popup=n.node_id,
        ).add_to(m)

    return m


def visualize_wind_vectors(nodes: List[IoTNode], scale: float = 0.005):
    """Draw wind direction arrows for each node with color-coded speed."""
    first = nodes[0]
    m = folium.Map(location=[first.latitude, first.longitude], zoom_start=14)
    speeds = [n.wind_vector[0] for n in nodes]
    cmap = cm.linear.PuBu_09.scale(min(speeds), max(speeds))
    for n in nodes:
        folium.CircleMarker(
            [n.latitude, n.longitude],
            radius=3,
            color="black",
            fill=True,
            fill_color="black",
            fill_opacity=1,
            popup=n.node_id,
        ).add_to(m)
        speed, direction = n.wind_vector
        end_lat = n.latitude + scale * speed * math.cos(math.radians(direction))
        end_lon = n.longitude + scale * speed * math.sin(math.radians(direction))
        line = folium.PolyLine(
            [[n.latitude, n.longitude], [end_lat, end_lon]],
            color=cmap(speed),
            weight=2,
        ).add_to(m)
        PolyLineTextPath(
            line,
            "→",
            repeat=True,
            offset=5,
            attributes={"fill": cmap(speed), "font-weight": "bold"},
        ).add_to(m)
    cmap.caption = "Wind speed"
    cmap.add_to(m)
    return m


def visualize_metric_folium(
    nodes: List[IoTNode],
    metric: str,
    accessor: Optional[Callable[[IoTNode], float]] = None,
    colormap=cm.linear.YlOrRd_09,
):
    """Color nodes by ``metric`` using a linear colormap."""
    first = nodes[0]
    m = folium.Map(location=[first.latitude, first.longitude], zoom_start=14)
    values = [accessor(n) if accessor else getattr(n, metric) for n in nodes]
    cmap = colormap.scale(min(values), max(values))
    for n in nodes:
        val = accessor(n) if accessor else getattr(n, metric)
        folium.CircleMarker(
            [n.latitude, n.longitude],
            radius=4,
            color=cmap(val),
            fill=True,
            fill_color=cmap(val),
            popup=f"{n.node_id} {metric}: {val:.2f}",
        ).add_to(m)
    cmap.caption = metric.capitalize()
    cmap.add_to(m)
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
    #stream_data(nodes, topic="iot_fire_data", interval=2)
