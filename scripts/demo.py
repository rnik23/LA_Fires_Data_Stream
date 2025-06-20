#!/usr/bin/env python3
"""Utility script to run the LA Fires data stream demo."""
from __future__ import annotations

from lafires import (
    initialize_nodes_center_grid,
    visualize_nodes_folium,
    visualize_temperature_heatmap,
    visualize_metric_folium,
    visualize_wind_vectors,
    stream_data,
)


if __name__ == "__main__":
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
    # Uncomment to stream data
    stream_data(nodes, topic="iot_fire_data", interval=5)

