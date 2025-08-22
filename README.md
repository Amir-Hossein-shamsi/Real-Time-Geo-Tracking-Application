# Enterprise Package Tracking System

>![Enterprise Grade](https://img.shields.io/badge/Enterprise-Grade-blue)
![Real-time Tracking](https://img.shields.io/badge/Real--time-Tracking-green)

>![OSRM](https://img.shields.io/badge/OSRM-Route_Optimization-000000?logo=openstreetmap&logoColor=white)

>![Apache Kafka](https://img.shields.io/badge/Apache%20Kafka-000?style=for-the-badge&logo=apachekafka)
>![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Redis](https://img.shields.io/badge/redis-%23DD0031.svg?style=for-the-badge&logo=redis&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-%234ea94b.svg?style=for-the-badge&logo=mongodb&logoColor=white)
![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)

## Overview

The Enterprise Package Tracking System is a high-performance, scalable solution for real-time package monitoring and delivery optimization. Built with cutting-edge technologies, this system provides seamless tracking capabilities with enterprise-grade reliability and performance.

## 🚀 Key Features

- **Real-time Location Tracking**: WebSocket-based live tracking with sub-second updates
- **Intelligent Route Optimization**: AI-powered routing with multi-stop branch optimization
- **Scalable Architecture**: Microservices-based design with horizontal scaling capabilities
- **High Availability**: Redis-based caching and Kafka message queue for fault tolerance
- **Advanced Geocoding**: Reverse geocoding integration for address approximation
- **Enterprise Analytics**: Comprehensive data collection for business intelligence

## 🛠️ Technology Stack

### Core Technologies
- **FastAPI**: High-performance Python web framework with automatic OpenAPI documentation
- **MongoDB**: NoSQL database for flexible data storage and retrieval
- **Redis**: In-memory data store for caching and real-time pub/sub
- **Kafka**: Distributed event streaming platform for message queuing
- **Docker**: Containerization for consistent deployment across environments

### Specialized Components
- **OSRM**: Open Source Routing Machine for optimized path calculation
- **WebSocket**: Real-time bidirectional communication protocol
- **Haversine Formula**: Precise distance calculations between geographic points

## 📦 Enterprise Features

### Advanced Routing Algorithm
Our system implements a sophisticated TSP (Traveling Salesman Problem) solver that:
- Dynamically selects optimal branch locations based on package origin and destination
- Minimizes detour distance while maximizing delivery efficiency
- Classifies trips into categories (inner_city, medium_trip, inter_city) for appropriate routing

### Real-time Data Pipeline
- **Kafka Producers**: Generate package update events at configurable intervals
- **Kafka Consumers**: Process events for geocoding and analytics
- **Redis Pub/Sub**: Broadcast location updates to connected clients in real-time

### High Availability Design
- Redis caching layer for fast status retrieval
- MongoDB fallback for data persistence
- Automated failover mechanisms
- Horizontal scaling capabilities

## 🚀 Quick Start

### Prerequisites
- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB RAM minimum (8GB recommended)

### Deployment

1. **Clone and setup**:
```bash
git clone https://github.com/Amir-Hossein-shamsi/Real-Time-Geo-Tracking-Application
cd enterprise-package-tracking
```

2. **Start the system**:
```bash
docker-compose up -d
```

3. **Verify services**:
```bash
docker-compose ps
```

4. **Access the application**:
- API Documentation: http://localhost:8000/docs
    > swaggerUI

## 🔧 Configuration

### Environment Variables
```env
MONGO_URL=mongodb://mongo:27017
REDIS_URL=redis://redis:6379
KAFKA_BOOTSTRAP_SERVERS=kafka:29092
OSRM_URL=http://osrm:5000
```

### Performance Tuning
For enterprise deployments, consider adjusting:
- Kafka partition counts based on expected load
- MongoDB replica set configuration
- Redis memory policies and persistence settings
- OSRM pre-processing for regional maps

## 📊 API Usage Examples

### Create a Package
```python
import requests

payload = {
    "origin_lat": 35.6892,
    "origin_lon": 51.3890,
    "dest_lat": 36.3000,
    "dest_lon": 59.6057
}

response = requests.post("http://localhost:8000/packages", json=payload)
print(response.json())
```

### Track Package (WebSocket)
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/PKG123456789');
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('New location:', data.currentLocation);
};
```

### Get Package Status
```bash
curl http://localhost:8000/packages/PKG123456789/status
```

## 📄 License

> MIT License

