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
    def __init__(self, node_id, latitude, longitude):
        self.node_id = node_id
        self.latitude = latitude
        self.longitude = longitude
        self.temperature = random.uniform(15, 25)  # Initial temperature (°C)
        self.wind_vector = (random.uniform(0, 10), random.uniform(0, 10))  # (speed, direction)
        self.humidity = random.uniform(30, 50)  # % humidity

    def generate_data(self):
        # Simulate sensor data with noise
        self.temperature += random.uniform(-0.5, 0.5)  # Add some noise
        self.wind_vector = (
            random.uniform(0, 10),
            random.uniform(0, 360)
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
def initialize_nodes(grid_size, start_lat, start_long, step=0.01):
    nodes = []
    for i in range(grid_size):
        for j in range(grid_size):
            node_id = f"node_{i}_{j}"
            latitude = start_lat + (i * step)
            longitude = start_long + (j * step)
            nodes.append(IoTNode(node_id, latitude, longitude))
    return nodes

# Example: 5x5 grid starting at GPS coordinates
nodes = initialize_nodes(grid_size=5, start_lat=34.0522, start_long=-118.2437)

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
