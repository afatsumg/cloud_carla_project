# Cloud CARLA Project Documentation

## Project Overview

This is a cloud-based autonomous driving simulation system that uses **CARLA** (an open-source autonomous driving simulator) to generate sensor data (camera and LiDAR) and store the results in AWS S3. The project is containerized using Docker and can be deployed on cloud infrastructure with GPU support.

## Architecture

The project follows a client-server architecture:

- **CARLA Server**: Runs the simulation engine in headless mode
- **CARLA Client**: Connects to the server, spawns vehicles, attaches sensors, and processes data
- **AWS S3**: Cloud storage for simulation results

## Project Structure

```
cloud_carla_project/
├── Dockerfile                 # Docker container definition
├── docker-compose.yml        # Docker Compose orchestration
├── requirements.txt          # Python dependencies
├── scenarios/                # YAML configuration files
│   └── scenario_01.yaml     # Test scenario configuration
└── src/                      # Source code
    ├── main.py              # Main simulation runner
    ├── carla_utils.py       # CARLA simulation utilities
    ├── parser.py            # YAML scenario parser
    └── s3_uploader.py       # AWS S3 upload handler
```

## Dependencies

**requirements.txt**
```
pyyaml                      # YAML parsing for scenarios
numpy                       # Numerical operations
opencv-python              # Image processing
carla==0.9.15              # CARLA simulator (must match server version)
boto3                      # AWS S3 integration
```

## Core Components

### 1. Dockerfile

A containerized Python environment with system dependencies for CARLA and OpenCV. See the actual Dockerfile in the repository for implementation details.

### 2. docker-compose.yml

Orchestrates CARLA server and client services with GPU support. Defines two services: CARLA server (headless mode) and CARLA client (simulation runner). See the docker-compose.yml file in the repository for full configuration.

### 3. Scenario Configuration (scenarios/scenario_01.yaml)

Defines the simulation parameters including map, weather, sensors, vehicle model, and metrics. See scenario_01.yaml in the repository for the complete configuration.

---

## Source Code Details

### main.py

The main simulation orchestrator that:
1. Prepares output directories
2. Loads scenario configuration
3. Initializes CARLA simulation
4. Spawns vehicle and attaches sensors
5. Runs simulation for 10 seconds
6. Compresses and uploads results to S3

See src/main.py in the repository for the complete implementation.

**Key Features:**
- Configurable scenario loading via YAML
- Automatic data directory creation
- 10-second simulation duration with data collection
- Proper sensor cleanup to avoid file locks
- Automatic compression (tar.gz) of sensor data
- AWS S3 integration for cloud storage

---

### carla_utils.py

Core CARLA simulation management utility class that handles:
- CARLA client connection management
- World setup with weather presets
- Vehicle spawning with fallback mechanisms
- RGB camera sensor attachment (1280x720, 10 FPS)
- LiDAR sensor attachment (32 channels, 50m range, 10 FPS)
- Proper resource cleanup

See src/carla_utils.py in the repository for the complete implementation.

**Key Features:**
- CARLA client connection management
- World setup with weather presets
- Vehicle spawning with fallback mechanisms
- RGB camera sensor (1280x720, 10 FPS)
- LiDAR sensor (32 channels, 50m range, 10 FPS)
- Proper resource cleanup

---

### s3_uploader.py

AWS S3 integration module for uploading simulation results that:
- Verifies file existence before upload
- Reports file size in MB
- Handles AWS credential validation
- Provides comprehensive error handling for network and client errors

See src/s3_uploader.py in the repository for the complete implementation.

**Key Features:**
- File existence verification
- File size reporting (MB)
- Comprehensive error handling
- AWS credential validation
- Exception handling for network errors

---

## Data Flow

```
┌─────────────────────────────────────────────────────────┐
│  main.py - Simulation Orchestrator                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  1. Load Scenario (parser.py)                           │
│     └─→ scenario_01.yaml                                │
│                                                          │
│  2. Initialize CARLA (carla_utils.py)                   │
│     └─→ Connect to CARLA Server                         │
│                                                          │
│  3. Setup World & Spawn Vehicle                         │
│     └─→ Load map, apply weather, spawn car              │
│                                                          │
│  4. Attach Sensors                                      │
│     ├─→ RGB Camera (saves PNG frames)                   │
│     └─→ LiDAR (saves PLY point clouds)                  │
│                                                          │
│  5. Run Simulation (10 seconds)  that:
- Loads and parses YAML scenario files
- Extracts simulation parameters (weather, sensors, vehicle config)
- Provides default value fallbacks

See src/parser.py in the repository for the complete implementation.. Start CARLA server
# 2. Connect client
# 3. Run 10-second simulation
# 4. Collect sensor data
# 5. Upload results to S3
```

### Output Files

**Local Storage** (`/app/output/`):
- `camera/` - RGB image frames (PNG, numbered `000000.png`, etc.)
- `lidar/` - Point cloud data (PLY, numbered `000000.ply`, etc.)
- `results.tar.gz` - Compressed archive of all data

**Cloud Storage** (AWS S3):
- `results_[timestamp].tar.gz` - Timestamped archive in S3 bucket

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `CARLA_HOST` | CARLA server hostname/IP | `carla-server` or `localhost` |
| `AWS_BUCKET_NAME` | S3 bucket for uploads | `my-carla-results` |
| `AWS_ACCESS_KEY_ID` | AWS credentials | (from AWS IAM) |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials | (from AWS IAM) |

## Known Implementation Details

1. **File Lock Prevention**: Sensors are properly stopped before attempting to read/compress files
2. **OS Independence**: Uses `os.path.join()` for cross-platform path handling
3. **Error Tolerance**: Graceful fallback if specified vehicle model not found
4. **Data Synchronization**: Camera and LiDAR both run at 10 FPS for temporal alignment
5. **Buffer Time**: 2-second delay after cleanup ensures OS writes all data before compression

## Future Enhancements

- Multi-scenario batch processing
- Vehicle routing optimization
- Sensor data validation and quality metrics
- Real-time visualization option
- Multiple vehicle simulations
- Custom weather scheduling
- Data format conversions (PLY to other formats)
