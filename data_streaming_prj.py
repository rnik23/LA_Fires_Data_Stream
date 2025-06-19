#!/usr/bin/env python
# coding: utf-8

# # Simulating IoT Devices for Real-Time Data Streaming with Kafka"
# 

# ## 2. Setup and Installation
# 

# In[3]:


import random
import time
import json
import folium
import requests
import branca.colormap as cm



def get_current_weather(latitude, longitude):
    """Fetch current temperature and humidity from Open-Meteo."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current_weather": True,
        "hourly": "relative_humidity_2m",
        "timezone": "UTC",
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        temp = data.get("current_weather", {}).get("temperature")
        humidity = None
        hourly = data.get("hourly", {})
        if hourly.get("relative_humidity_2m"):
            humidity = hourly["relative_humidity_2m"][0]
        return temp, humidity
    except Exception:
        return None, None

try:
    from kafka import KafkaProducer
    producer = KafkaProducer(
        bootstrap_servers=["localhost:9092"],
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
except Exception:
    class DummyProducer:
        """Fallback producer used when Kafka is unavailable."""

        def send(self, topic, value):
            print(f"[DummyProducer] {topic}: {value}")

    producer = DummyProducer()


# ## 3. Code Sections
# 

# ### 1. Simulating IoT Devices:
# 
# 

# In[4]:


# IoT node class
class IoTNode:
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

    def __init__(self, node_id, latitude, longitude, wind_direction="N"):
        self.node_id = node_id
        self.latitude = latitude
        self.longitude = longitude

        # Pull baseline weather conditions for this location
        temp, hum = get_current_weather(latitude, longitude)
        self.temperature = temp if temp is not None else random.uniform(15, 25)
        self.humidity = hum if hum is not None else random.uniform(30, 50)

        # Wind vector uses user-supplied direction with random speed
        self.wind_vector = (
            random.uniform(0, 10),
            self.DIRECTIONS.get(wind_direction.upper(), 0),
        )

    def generate_data(self):
        # Simulate sensor data with noise
        self.temperature += random.uniform(-0.5, 0.5)  # Add some noise
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

# ### 2.Data Generation:
# 
#  

# In[5]:


# Create a grid of IoT nodes
def initialize_nodes(grid_size, start_lat, start_long, step=0.01, wind_direction="N"):
    nodes = []
    for i in range(grid_size):
        for j in range(grid_size):
            node_id = f"node_{i}_{j}"
            latitude = start_lat + (i * step)
            longitude = start_long + (j * step)
            nodes.append(IoTNode(node_id, latitude, longitude, wind_direction=wind_direction))
    return nodes


def initialize_nodes_center_grid(grid_size, center_lat, center_long, lat_spread=0.01, lon_spread=0.01, wind_direction="N"):
    """Create a grid of nodes centered around a coordinate.

    The grid is spread evenly across the latitude and longitude ranges
    defined by ``lat_spread`` and ``lon_spread`` (on either side of the
    center point).
    """
    nodes = []
    lat_start = center_lat - lat_spread
    lon_start = center_long - lon_spread
    # Avoid division by zero when grid_size == 1
    lat_step = (2 * lat_spread) / max(grid_size - 1, 1)
    lon_step = (2 * lon_spread) / max(grid_size - 1, 1)
    for i in range(grid_size):
        for j in range(grid_size):
            latitude = lat_start + i * lat_step
            longitude = lon_start + j * lon_step
            node_id = f"node_{i+1}_{j+1}"
            nodes.append(IoTNode(node_id, latitude, longitude, wind_direction=wind_direction))
    return nodes

# Example: grid of nodes centered at given coordinates
nodes = initialize_nodes_center_grid(
    grid_size=5,
    center_lat=34.0522,
    center_long=-118.2437,
    lat_spread=0.02,
    lon_spread=0.02,
    wind_direction="NE",
)

# #### show geolocation on map:

# In[6]:


import folium

# Function to visualize nodes on a map
def visualize_nodes_folium(nodes):
    """Basic map showing node positions."""
    first_node = nodes[0]
    m = folium.Map(location=[first_node.latitude, first_node.longitude], zoom_start=14)
    for node in nodes:
        folium.Marker([node.latitude, node.longitude], popup=node.node_id).add_to(m)
    return m


def visualize_metric_folium(nodes, metric, accessor=None):
    """Visualize a numeric node attribute on a map using color scaling.

    Parameters
    ----------
    nodes : list
        List of ``IoTNode`` objects.
    metric : str
        Attribute name to visualize.
    accessor : callable, optional
        If provided, called with a node to get the value instead of
        ``getattr(node, metric)``.
    """
    first_node = nodes[0]
    m = folium.Map(location=[first_node.latitude, first_node.longitude], zoom_start=14)
    if accessor is None:
        values = [getattr(n, metric) for n in nodes]
    else:
        values = [accessor(n) for n in nodes]
    colormap = cm.linear.YlOrRd_09.scale(min(values), max(values))
    for node in nodes:
        val = accessor(node) if accessor else getattr(node, metric)
        folium.CircleMarker(
            [node.latitude, node.longitude],
            radius=6,
            color=colormap(val),
            fill=True,
            fill_color=colormap(val),
            popup=f"{node.node_id} {metric}: {val:.2f}",
        ).add_to(m)
    colormap.caption = metric.capitalize()
    colormap.add_to(m)
    return m

# Visualize the IoT nodes
m = visualize_nodes_folium(nodes)
m.save("iot_nodes_map.html")  # Save node positions map

# Create additional maps for each metric
temp_map = visualize_metric_folium(nodes, "temperature")
temp_map.save("iot_temperature_map.html")

humidity_map = visualize_metric_folium(nodes, "humidity")
humidity_map.save("iot_humidity_map.html")

# Visualize wind speed (direction is shown in popup)
wind_speed_map = visualize_metric_folium(
    nodes,
    "wind_speed",
    accessor=lambda n: n.wind_vector[0],
)
wind_speed_map.save("iot_wind_speed_map.html")



# ### 3. Kafka Integration:
# 
# 

# #### Streaming Data to Kafka

# In[ ]:


def stream_data(nodes, topic, interval=1):
    while True:
        for node in nodes:
            data = node.generate_data()
            producer.send(topic, value=data)  # Send data to Kafka
            print(f"Sent: {data}")
        time.sleep(interval)  # Wait before the next batch

# Stream data to Kafka topic 'iot_fire_data'
stream_data(nodes, topic='iot_fire_data', interval=2)


# ### 4. Testing the Stream:
# 
# 

# ## 4. Documentation
# 

# 

# 
