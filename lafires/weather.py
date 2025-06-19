"""Weather helper utilities."""
from __future__ import annotations

import random
from typing import Generator
import requests

__all__ = [
    "get_current_weather",
    "wind_generator",
]


def get_current_weather(
    latitude: float,
    longitude: float,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Return (temperature, humidity, wind_speed, wind_direction) via Open-Meteo."""
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
        resp.raise_for_status()
        data = resp.json()

        cw = data.get("current_weather", {})
        temp = cw.get("temperature")
        wind_speed = cw.get("windspeed")
        wind_dir = cw.get("winddirection")

        hourly = data.get("hourly", {})
        hum_list = hourly.get("relative_humidity_2m", [])
        humidity = hum_list[0] if hum_list else None

        return temp, humidity, wind_speed, wind_dir
    except Exception:
        return None, None, None, None


def wind_generator(
    base_speed: float,
    phi: float = 0.8,
    sigma: float = 0.5,
    gust_prob: float = 0.05,
    gust_min: float = 5.0,
    gust_max: float = 15.0,
) -> Generator[float, None, None]:
    """Yield wind speeds with occasional gusts."""
    prev = base_speed
    while True:
        if random.random() < gust_prob:
            speed = prev + random.uniform(gust_min, gust_max)
        else:
            speed = base_speed + phi * (prev - base_speed) + random.gauss(0, sigma)
        prev = speed
        yield max(speed, 0.0)
