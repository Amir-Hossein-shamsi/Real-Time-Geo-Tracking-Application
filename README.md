# Real-Time Geo-Tracking Application

This is a proof-of-concept application demonstrating a real-time package tracking system. It uses FastAPI for the backend, MongoDB for data storage, Redis for messaging, and Folium for interactive map visualization on the client side.

 <!-- Placeholder for a cool demo GIF -->

## ✨ Features

*   **Real-Time Location Updates**: Track package movements on a live map without refreshing the page, powered by WebSockets.
*   **Dynamic Route Calculation**: Generates optimal driving routes between origin and destination using the OSRM engine.
*   **Smart Waypoint Chaining**: Automatically identifies and includes optimal intermediate company branches in the route to simulate a realistic logistics chain.
*   **Interactive Map Visualization**: Uses Folium to render beautiful, interactive maps showing the route, branch locations, and the package's animated position.
*   **Scalable Pub/Sub Architecture**: Leverages Redis for a decoupled and scalable publish/subscribe system to handle location updates.
*   **Asynchronous Backend**: Built with FastAPI for high performance and asynchronous capabilities.

## 🏗️ Architecture

The application follows a decoupled, event-driven architecture.

1.  **Package Creation**: A client sends a `POST` request to `/packages` with origin and destination coordinates.
2.  **Route Planning**: The FastAPI backend calculates the optimal route via OSRM, including a dynamically generated chain of intermediate branches.
3.  **Data Persistence**: The new package, its route, and branch chain are stored in a MongoDB collection.
4.  **Movement Simulation**: A background thread (`simulate_movement`) is spawned for the new package. It iterates through the route coordinates and publishes each new location to a `package_updates` channel in Redis.
5.  **Update Listener**: A long-running background thread (`redis_listener`) subscribes to the `package_updates` channel.
6.  **Fan-Out**: When the listener receives a location update from Redis, it:
   *   Updates the package's `currentLocation` in MongoDB.
   *   Broadcasts the new location to all connected WebSocket clients for that specific package.
7.  **Frontend**: The client-side map page establishes a WebSocket connection. Injected JavaScript listens for incoming location data and smoothly animates the package marker on the Folium map.

### Data Flow Diagram

```mermaid
sequenceDiagram
    participant Client
    participant FastAPI
    participant OSRM
    participant MongoDB
    participant MovementSim as Movement Sim (Thread)
    participant Redis
    participant Listener as Listener (Thread)
    participant WebSocket

    Client->>+FastAPI: POST /packages (origin, dest)
    FastAPI->>+MongoDB: Find nearby branches
    MongoDB-->>-FastAPI: Branch data
    FastAPI->>+OSRM: Get route with waypoints
    OSRM-->>-FastAPI: Route coordinates
    FastAPI->>+MongoDB: Create package document
    MongoDB-->>-FastAPI: packageId
    FastAPI-->>-Client: { "packageId": "PKG123" }
    FastAPI-)-MovementSim: Start simulate_movement("PKG123")

    loop For each point in route
        MovementSim->>+Redis: PUBLISH package_updates (location)
        Redis-->>-MovementSim:
        MovementSim->>MovementSim: sleep()
    end

    Listener->>+Redis: SUBSCRIBE package_updates
    Note over Redis, Listener: Listener is always running

    Redis-->>Listener: Receives location update
    Listener->>+MongoDB: UPDATE package location
    MongoDB-->>-Listener:
    Listener->>+FastAPI: run_coroutine_threadsafe(send_to_clients)
    FastAPI-->>-Listener:

    Client->>+FastAPI: GET /packages/PKG123/map
    FastAPI->>+MongoDB: Get package data
    MongoDB-->>-FastAPI:
    FastAPI-->>-Client: HTML with Folium map & JS

    Client->>+WebSocket: Connect to /ws/PKG123
    WebSocket-->>-Client: Connection accepted

    loop On location update received by Listener
        FastAPI->>+WebSocket: PUSH location update
        WebSocket-->>-Client: Receives JSON update
        Note over Client: JS animates marker on map
    end
```

## 🛠️ Tech Stack

*   **Backend**: FastAPI, Uvicorn
*   **Database**: MongoDB
*   **Messaging / Caching**: Redis
*   **Mapping**: Folium
*   **Routing**: Project-OSRM
*   **Python Libraries**: `pymongo`, `redis-py`, `requests`

## 🚀 Getting Started

### Prerequisites

*   Python 3.9+
*   Docker and Docker Compose (recommended for running MongoDB and Redis)

### Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone github.com:Amir-Hossein-shamsi/Real-Time-Geo-Tracking-Application.git
    cd geortacking-app
    ```

2.  **Create a virtual environment and activate it:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    # On Windows: .venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run MongoDB and Redis using Docker:**
    ```bash
    docker run -d -p 27017:27017 --name geo-mongo mongo:latest
    docker run -d -p 6379:6379 --name geo-redis redis:latest
    # or use docker-compose.yml as like as me
    # docker-compose up -d
    ```

5.  **Populate the database with dummy branch data:**
    ```bash
    python models/dummy.py
    ```

6.  **Run the FastAPI application:**
    ```bash
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    ```

## 📖 API Endpoints

### Create a Package

*   **URL**: `/packages`
*   **Method**: `POST`
*   **Description**: Creates a new package, calculates its route, and starts the movement simulation.
*   **Request Body**:
    ```json
    {
      "origin_lat": 35.73,
      "origin_lon": 51.37,
      "dest_lat": 35.68,
      "dest_lon": 51.42
    }
    ```
*   **Success Response (200 OK)**:
    ```json
    {
      "packageId": "PKG1678886400",
      "branches": [
        {
          "branchId": "B006",
          "name": "Branch F",
          "lat": 35.73285005077543,
          "lon": 51.377394476782776
        }
      ],
      "message": "Package created and simulation started"
    }
    ```

### Get Package Map

*   **URL**: `/packages/{package_id}/map`
*   **Method**: `GET`
*   **Description**: Returns an HTML page with a live-tracking map for the specified package.

### WebSocket Connection

*   **URL**: `/ws/{package_id}`
*   **Description**: Establishes a WebSocket connection to receive real-time location updates for the package.

## 🕹️ How to Use

1.  Follow the **Installation & Setup** steps above.
2.  Use a tool like `curl` or an API client (e.g., Postman) to send a `POST` request to `http://localhost:8000/packages` with your desired coordinates.
    ```bash
    curl -X POST -H "Content-Type: application/json" \
    -d '{"origin_lat": 35.73, "origin_lon": 51.37, "dest_lat": 35.68, "dest_lon": 51.42}' \
    http://localhost:8000/packages
    ```
3.  Copy the `packageId` from the response.
4.  Open your web browser and navigate to `http://localhost:8000/packages/YOUR_PACKAGE_ID/map` (replace `YOUR_PACKAGE_ID` with the actual ID).
5.  Watch the 🚚 icon move along the calculated route in real-time!
