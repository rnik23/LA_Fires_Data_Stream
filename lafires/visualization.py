"""Visualization utilities for IoT node data."""
from __future__ import annotations

import math
import statistics
from typing import Callable, List, Optional

import folium
import branca.colormap as cm
from folium.plugins import HeatMap, PolyLineTextPath

from .nodes import IoTNode

__all__ = [
    "visualize_nodes_folium",
    "visualize_temperature_heatmap",
    "visualize_wind_vectors",
    "visualize_metric_folium",
]


def visualize_nodes_folium(nodes: List[IoTNode]):
    """Display node markers on a folium map."""
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


def visualize_temperature_heatmap(nodes: List[IoTNode], zoom_start: int = 14):
    """Render a heatmap that highlights temperature anomalies."""
    first = nodes[0]
    m = folium.Map(location=[first.latitude, first.longitude], zoom_start=zoom_start)

    temps = [n.temperature for n in nodes]
    mean_temp = statistics.mean(temps)
    std_temp = statistics.pstdev(temps) or 1

    z_threshold = 3.0
    lower, upper = -z_threshold * std_temp, z_threshold * std_temp

    heat_data = []
    for n in nodes:
        z = (n.temperature - mean_temp) / std_temp
        z_clamped = max(lower, min(upper, z))
        norm = (z_clamped - lower) / (upper - lower)
        if abs(z) < z_threshold:
            weight = norm * 0.5
        else:
            weight = 0.5 + (abs(z_clamped) - (z_threshold * std_temp)) / ((z_threshold * std_temp) - lower) * 0.5
        heat_data.append([n.latitude, n.longitude, weight])

    gradient = {
        0.0: "blue",
        0.25: "cyan",
        0.5: "lime",
        0.75: "yellow",
        1.0: "red",
    }

    HeatMap(
        heat_data,
        min_opacity=0.3,
        radius=50,
        blur=35,
        max_zoom=zoom_start,
        gradient=gradient,
    ).add_to(m)

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

