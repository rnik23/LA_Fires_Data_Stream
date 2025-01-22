# LA_Fires_Data_Stream
![Pipeline Architecture Diagram](Data_Flow_Diagram(DFD).png)
# LA Fires Data Stream Project

## **Project Overview**
This project simulates an IoT-based pipeline for monitoring and predicting the spread of fires, inspired by the devastating Los Angeles fires. The system uses simulated sensor data to stream real-time information about environmental factors, processes it for anomaly detection and fire projection, and visualizes insights through an analytics dashboard.

The goal is to build end-to-end data engineering and analytics skills while creating a meaningful tool for understanding fire dynamics.

---

## **Data Flow Overview**
1. **IoT Data Source**:
   - **Node Grid**: Simulates a network of sensors with unique IDs and GPS coordinates.
   - **Data Fields**: Temperature, wind vector, humidity, air quality, and visibility, with timestamps.

2. **Event Generator**:
   - Adds realistic variability (e.g., Gaussian noise) to simulate sensor behavior.
   - Detects anomaly spikes using statistical thresholds (e.g., standard deviation, rolling averages).

3. **Kafka Broker**:
   - **Input Topic**: Raw IoT data (`raw_iot_data`).
   - **Partitions**: Data partitioned by node IDs or regions for parallel processing.

4. **Stream Processing**:
   - **Anomaly Detection**: Identifies temperature spikes and calculates severity scores.
   - **Data Aggregation**: Groups data by region, calculates average severity, and projects fire spread using wind vectors.
   - **Output Topic**: Processed data (`processed_iot_data`).

5. **Data Sink**:
   - Stores processed data in PostgreSQL with structured fields for efficient querying.

6. **Visualization**:
   - **Heat Map**: Displays regions with varying severity levels using libraries like Folium or Plotly.
   - **Spread Projection**: Overlays wind-based fire drift predictions.

---

## **Key Features**
- **Real-Time Data Simulation**: Generate IoT sensor data streams for environmental monitoring.
- **Stream Processing**: Use Kafka to detect anomalies and project fire spread.
- **Interactive Visualization**: Create heat maps and projections to analyze fire dynamics.
- **Pipeline from Root to Analytics**: Demonstrates skills in data pipelines, processing, analysis, and visualization.

---

## **Project Goals**
- **Skill Development**:
  - Real-time data streaming with Kafka.
  - Data processing and analysis in Python.
  - End-to-end data pipelines.
  - Visualization using Python libraries.
- **Fire Monitoring Simulation**:
  - Build a system that mimics real-world scenarios to monitor fire dynamics effectively.

---

## **Project Structure**
- **Jupyter Notebook**: Prototyping and initial implementation.
- **Scripts**:
  - Sensor Simulation: Generates IoT data.
  - Kafka Producer/Consumer: Handles data streaming.
  - Data Processing: Detects anomalies and projects fire spread.
  - Visualization: Creates heat maps and fire drift overlays.
- **Database**: PostgreSQL for structured storage of processed data.
- **Dashboard**: Optional future step to host a real-time interface.

---

## **How to Use**
1. Clone the repository:
   ```bash
   git clone https://github.com/rnik23/LA_Fires_Data_Stream.git
   ```

2. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the Jupyter Notebook to:
   - Simulate IoT data.
   - Stream data to Kafka.
   - Process and visualize fire dynamics.

4. Check out the Miro Board for the pipeline architecture [here](https://miro.com/welcomeonboard/ZVdFVUVrMzdWKzRGTFVIOFYyS0RwY0ZPMHdTVGV2Nkswa0hqRDZOMjVaQnBuTmp6MW13d0JrcHhZdHhZY1huVlRGcUd2dVdmd2kxYUFBSDRDem1jNGlxTnpGTmhDczNyYkZOQTJja2V1WkdUVjdwaDFRL1RvNFJLNEF2TFZ4b2UhZQ==?share_link_id=330959544685).

---

## **Planned Enhancements**
- **Realistic Fire Simulation**: Model fire dynamics more accurately.
- **Dashboard Hosting**: Use Streamlit or Dash for a real-time interface.
- **Advanced Analytics**: Implement machine learning for fire prediction.
- **Scalability**: Containerize the pipeline using Docker for production deployment.

---

## **Acknowledgments**
This project is inspired by the need to understand and mitigate the devastating impact of wildfires. Thanks to the open-source community for the tools and resources that make this possible.

---

## **Connect with Me**
- LinkedIn: [Your LinkedIn Profile](https://www.linkedin.com/in/rnik23/)
- GitHub: [LA Fires Repo](https://github.com/rnik23/LA_Fires_Data_Stream)


