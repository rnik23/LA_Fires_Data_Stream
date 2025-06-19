"""Simulation of IoT nodes for fire monitoring."""
from __future__ import annotations

import random
from typing import List

from .weather import get_current_weather, wind_generator

__all__ = [
    "IoTNode",
    "initialize_nodes_center_grid",
]


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
        base_wind_speed: float,
        base_wind_dir: float,
        wind_direction: str = "N",
    ) -> None:
        self.node_id = node_id
        self.latitude = latitude
        self.longitude = longitude
        self.temperature = temperature
        self.humidity = humidity
        self.base_wind_speed = base_wind_speed
        self.base_wind_dir = base_wind_dir
        self.wind_vector = (
            random.uniform(0, 10),
            self.DIRECTIONS.get(wind_direction.upper(), 0),
        )
        self.wind_stream = wind_generator(base_wind_speed)

    def generate_data(self) -> dict:
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
    center_temp, center_hum, wind_speed, wind_dir = get_current_weather(center_lat, center_long)
    if center_temp is None:
        center_temp = random.uniform(15, 25)
    if center_hum is None:
        center_hum = random.uniform(30, 50)
    if wind_speed is None:
        wind_speed = random.uniform(0, 5)
    if wind_dir is None:
        wind_dir = IoTNode.DIRECTIONS.get(wind_direction, 0)

    nodes: List[IoTNode] = []
    lat_start = center_lat - lat_spread
    lon_start = center_long - lon_spread
    lat_step = (2 * lat_spread) / max(grid_size - 1, 1)
    lon_step = (2 * lon_spread) / max(grid_size - 1, 1)

    noise_pct = 0.02

    for i in range(grid_size):
        for j in range(grid_size):
            latitude = lat_start + i * lat_step
            longitude = lon_start + j * lon_step
            node_id = f"node_{i+1}_{j+1}"
            temp_noise = center_temp * random.uniform(-noise_pct, noise_pct)
            hum_noise = center_hum * random.uniform(-noise_pct, noise_pct)
            temp = center_temp + temp_noise
            hum = center_hum + hum_noise
            nodes.append(
                IoTNode(
                    node_id,
                    latitude,
                    longitude,
                    wind_direction=wind_direction,
                    temperature=temp,
                    humidity=hum,
                    base_wind_speed=wind_speed,
                    base_wind_dir=wind_dir,
                )
            )
    return nodes

