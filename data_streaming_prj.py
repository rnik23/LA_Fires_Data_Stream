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


def initialize_nodes_center(num_nodes, center_lat, center_long, lat_spread=0.01, lon_spread=0.01, wind_direction="N"):
    """Create nodes randomly distributed around a center coordinate."""
    nodes = []
    for i in range(num_nodes):
        latitude = center_lat + random.uniform(-lat_spread, lat_spread)
        longitude = center_long + random.uniform(-lon_spread, lon_spread)
        node_id = f"node_{i+1}"
        nodes.append(IoTNode(node_id, latitude, longitude, wind_direction=wind_direction))
    return nodes

# Example: randomly distributed nodes around a center coordinate
nodes = initialize_nodes_center(
    num_nodes=25,
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
    # Initialize the map centered around the first node
    first_node = nodes[0]
    m = folium.Map(location=[first_node.latitude, first_node.longitude], zoom_start=14)
    
    # Add nodes as markers on the map
    for node in nodes:
        folium.Marker([node.latitude, node.longitude], popup=node.node_id).add_to(m)
    
    return m

# Visualize the IoT nodes
m = visualize_nodes_folium(nodes)
m.save("iot_nodes_map.html")  # Save the map to an HTML file
m


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
