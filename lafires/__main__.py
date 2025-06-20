#!/usr/bin/env python3
"""Console entry point for the lafires package."""
from __future__ import annotations

from . import (
    initialize_nodes_center_grid,
    visualize_nodes_folium,
    visualize_temperature_heatmap,
    visualize_metric_folium,
    visualize_wind_vectors,
    stream_data,
)

def main() -> None:
    """Run the LA Fires data stream demo."""
    nodes = initialize_nodes_center_grid(
        grid_size=1,
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

    # If you want to stream live data, uncomment:
    stream_data(nodes, topic="iot_fire_data", interval=5)
