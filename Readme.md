# FastAPI Wrapper for Microsoft Florence-2

A high-performance, production-ready wrapper for Microsoft's Florence-2 Vision-Language Model. This project provides both a FastAPI backend for programmatic access and a Chainlit frontend for interactive chat, integrated, seaweedFS for storage and auto auto purging of blobs AKA Object Life Cycle Management, and Logfire for observability.

## 🛠 Prerequisites

Before running this project, you need to create a Logfire Account (optional). If you don't create its totally fine, logs will be routed to standard docker logs. But if you need remote monitoring for logging, this project gives you that flexibility via logfirem,. 

#### 📉 Logfire 
For structured logging and monitoring. Create a free [Logfire](https://pydantic.dev/logfire) account and select the free plan. The [free plan](https://pydantic.dev/pricing) is very generous for localhost project. They give 10M span AKA logs. If you have ever used Grafana or Humio, you will find almost all the developer needful features in here. Create a project in Logfire and create a **write** token. Copy the token and put it in `.env`


3. Ensure the folder structure looks like this:
```
project_root/
├── api/
├── .env/
├── app/
├── .vscode/
├── hf_cache/
│   └── florence-2-large/
│       ├── config.json
│       ├── model.safetensors
│       ├── tokenizer.json
│       └── ... (other model files)
└── ... other files
```

Don't worry about the files inside hf_cache folder. You can skip creating this folder altogether. When you build the project for the first time, the project auto pulls the Florence Models from the internet and stores it here and mounts it via Docker Volumne. For code implementation details refer: [Florence Model Download Script](./download_model.sh)

## ⚙️ Configuration (.env)

Create a .env file in the root directory. Use the following template:

```
CHAINLIT_PORT=8010
FASTAPI_PORT=8020

API_WORKER_COUNT=2
DEV_MODE=false
SERVICE_NAME=florence-ai
LOG_LEVEL=DEBUG

# SKIP this section if you wish to run on CPU only
# ------ AMD RELATED ENV ------------
ACCELERATOR=rocm
AMD_GPU_DEVICE=/dev/dri
RENDER_GID=992
VIDEO_GID=44
HSA_OVERRIDE_GFX_VERSION=11.0.0
ROCM_ALLOW_UNSAFE_ASIC=1
TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1
MODEL_TIMEOUT=30
# ------ END  AMD RELATED ENV ------


# Postgres Configurations
POSTGRES_USER=admingithub
POSTGRES_PASSWORD=admin
POSTGRES_DB=florence_db
FLORENCE_SQL_SERVICE_NAME=florence_postgres
# Evaluated statically to prevent parsing issues inside the container
DATABASE_URL=postgresql+asyncpg://admin:admin@florence_postgres:5432/florence_db

LOGFIRE_TOKEN=<LOGFIRE TOKEN>

# Redis Configurations
FLORENCE_CACHE_SERVICE_NAME=florence-redis
REDIS_HOST=redis://florence-redis:6379

# SeaweedFS Configurations
FLORENCE_S3_SERVICE_NAME=florence-s3-seaweedfs
SEAWEEDFS_PORT=8030
BUCKET_TTL=1d

# Core variables for your config.py S3StorageClient
S3_BUCKET=florence-uploads
S3_ACCESS_KEY=adminseaweed
S3_SECRET_KEY=adminseaweed
S3_ENDPOINT_URL=http://florence-s3-seaweedfs:8000
S3_PUBLIC_URL=http://localhost:8030

# Native triggers read directly by 'weed mini'
S3_TABLE_BUCKET=
AWS_ACCESS_KEY_ID=adminseaweed
AWS_SECRET_ACCESS_KEY=adminseaweed
```

## 🐳 How to start the project?

#### 🛠️ Step 1: Hardware Acceleration & GPU Permissions (Linux/AMD Only)

By default, the project runs in CPU Mode. If you wish to run the model entirely on system RAM, skip this step and move directly to Step 2. If you have an AMD GPU, and its relevant drivers installed in your machine, you can enable ROCm acceleration. This requires mapping your host's hardware group IDs (GID) and setting specific flags so the container can talk to the GPU.

*1. Auto-Detect Hardware Config (Recommended)*
If using VS Code, we provide an automated task to detect your hardware IDs and inject the necessary ROCm optimization flags directly into your .env:

1. Press Ctrl+Shift+P -> Tasks: Run Task.
2. Select Florence: Auto-Detect Hardware Config.
3.  Verify: Open your .env. It will now contain the GIDs and GFX overrides specific to your machine.

*2. Understanding the GPU Parameters*

Whether using the Auto-Detect task or setting up manually, here is what these parameters do:

| Parameter | Value/Example | Description |
| :--- | :--- | :--- |
| ACCELERATOR | rocm | Enables AMD GPU acceleration logic in the code. |
| AMD_GPU_DEVICE | /dev/dri | The path to the GPU render nodes on your host. |
| RENDER_GID | 992 | Your host's 'render' group ID. Grants Docker permission to use the GPU.. |
| VIDEO_GID | 44 | Your host's 'video' group ID. Required for hardware video/image decoding. |
| HSA_OVERRIDE_GFX_VERSION | 11.0.0 | Forces ROCm to treat newer/integrated GPUs (like Radeon 780M/860M) as supported hardware. |
| ROCM_ALLOW_UNSAFE_ASIC | 1 | Allows ROCm to initialize on hardware not officially on the enterprise support list. |
| TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL | 1 | Enables a faster Triton-based backend for PyTorch on AMD hardware. |

*3. Manual GPU Setup (If Task Fails)*
If you aren't using VS Code, run these commands to find your IDs and add them to `.env`:
```
# Find your host IDs
RGID=$(getent group render | cut -d: -f3)
VGID=$(getent group video | cut -d: -f3)

# Add to .env
echo "ACCELERATOR=rocm" >> .env
echo "RENDER_GID=$RGID" >> .env
echo "VIDEO_GID=$VGID" >> .env
echo "HSA_OVERRIDE_GFX_VERSION=11.0.0" >> .env
```

#### Step 2: Build the Base Image
This project uses a Two-Stage Docker Build to maximize efficiency. By separating the heavy AI dependencies from the application code, we save time and data during rebuilds.

Dockerfile.base contains all the "heavy" dependencies like PyTorch, Transformers, and ROCm libraries. You have 2 options for this.

1. **Via CLI**: 
    ```
    docker build -f Dockerfile.base -t florence-base:latest .
    ```
2. **Via VS Code** (ctrl+shift+p: Run Task): Run the task "Florence: Build Base Image" from [vscode tasks](./.vscode/tasks.json)

#### Step 3: Build & Launch the Application
This step adds your application code on top of the base image. Since this project supports both hardware-accelerated and RAM-only execution, you must choose the launch command that matches your setup.

1. Build the Application Image
    ```
    docker build -t florence_ai:latest .
    ```
2. Start the Services
Based on your decision in Step 2, choose one of the following commands:

    + For AMD GPU Users:
    If you configured your hardware GIDs and wish to use ROCm acceleration, use the default compose file:
    ```
    docker compose up -d
    ```
    + For CPU / RAM-Only Users:
    If you do not have a GPU or wish to save power, use the CPU-optimized configuration to prevent Docker "device not found" errors:
    ```
    docker compose -f docker-compose.cpu.yaml up -d
    ```

## 🚀 Usage

Once the containers are up, you can access the Florence model through two interfaces:

| Interface  | URL                           | Description                                                  |
| ---------- | ----------------------------- | ------------------------------------------------------------ |
| _FastAPI_  | `http://localhost:8020`       | Rest API for programmatic inference and /predict endpoints   |
| _Chainlit_ | `http://localhost:8010`       | User-friendly chat interface for interactive image analysis. |
| _SeaweedFS_ | `http://localhost:8030`       | Seaweed interface for interactive image viewing. |


## ⚙️ Service Control (Selective Startup)

You can choose to run the API and the Chat UI together or independently. Control this via your `.env` file: Add the following flags in your `.env` and re build the container

| Flag | Logic | Result |
| :--- | :--- | :--- |
| `DISABLE_FLORENCE_API=true` | If present/non-empty | FastAPI (@ Port 8020) will **not** start. |
| `DISABLE_FLORENCE_CHAT=true` | If present/non-empty | Chainlit (@ Port 8010) will **not** start. |

**Note:** If both are left blank (default) or not present in `.env`, both services start in parallel. If both are set to `true`, the container will exit with an error to prevent wasted resources.


### 🛰️ API Feature: `store_image` Flag

When using the `/predict` endpoint, you can control whether the API behaves as a persistent storage service or a transient inference engine using the `store_image` boolean flag.

| Flag | Behavior | Response Format |
| :--- | :--- | :--- |
| `true` (Default) | **Persistent**: Both input and output images are uploaded to SeaweedFS S3. | Returns **Presigned S3 URLs**. |
| `false` | **Transient**: No files are stored in S3. Images are processed entirely in memory. | Returns **Base64 Encoded Strings**. |

#### Example Request (Curl)
```bash
curl -X 'POST' \
  'http://localhost:8020/v1/predict' \
  -H 'accept: application/json' \
  -H 'Content-Type: multipart/form-data' \
  -F 'task=<OD>' \
  -F 'file=@image.jpg' \
  -F 'store_image=false'
```

## Storage Management

All images (input and output) are automatically synced to your SeaweedFS instance, when using Chainlit. However while using FastAPI, you can control this behavior via `store_image` flag. This ensures that your local Docker container remains stateless and images are persisted safely.

## 📈 Monitoring & Logging

This project is integrated with Pydantic Logfire.

1. Production Mode (DEV_MODE=false): All logs and traces are sent to your Logfire dashboard. You must provide a valid LOGFIRE_TOKEN.
       Chainlit is run as background process and FastAPI is run as a PID 1 process.
2. Development Mode (DEV_MODE=true): Logfire is disabled, and logs are output to the standard console for easier local debugging.
       Neither Chainlit or FastAPI is run by default. Its left upto the developer to chose which they want to run. Commands are available in enterypoint.sh. Or you can run them using tasks available in .vscode/tasks.json


## 🚀 Key Enhancement: Singleton Model Worker & Scalable Backend

Unlike the [original implementation](https://github.com/askaresh/MS-Florence2/tree/main/app) which was strictly optimized for NVIDIA GPUs via CUDA, this wrapper is designed to be hardware-agnostic. 

A major architectural improvement in this wrapper is the decoupling of the Florence-2 Inference Engine from the Web Servers (FastAPI/Chainlit).

+ *Memory Efficiency*: Traditional wrappers load the model into every API worker process. By using a standalone [model_worker.py](./app/model_worker.py), only one instance of the 1.6GB Florence-2 model resides in memory, regardless of how many FastAPI or Chainlit instances are running.

+ *Scalable FastAPI via Gunicorn*: You can now scale the API throughput by increasing the API_WORKER_COUNT flag in your `.env`. Gunicorn will spawn multiple FastAPI workers to handle concurrent web requests, while they all share the single model worker via a Redis-backed queue.

+ Universal Hardware Support:

    + *CPU Support*: By utilizing a Python 3.11 base image and explicitly configuring the model to use torch.device("cpu"), this project can run on any standard PC, laptop, or server without a dedicated GPU.

    + *Portability*: This makes the project ideal for local development and cost-effective cloud deployments where expensive GPU instances aren't required.


<mark>Note</mark>: If ACCELERATOR is not set, the build process defaults to a lightweight CPU-only version of PyTorch to save space.

## Demo Screenshots
| Output Image | Description | 
| :---: | :---: |
| ![Output](./demo/chainlit_demo_1.png) | Florence via Chainlit. Task <OD> short for Object Detection |
| ![Output](./demo/fastapi_demo_1.png) | FastAPI /v1/tasks to get all tasks supported |
| ![Output](./demo/fastapi_demo_2.png) |  FastAPI /v1/predict Task <MORE_DETAIL_CAPTION>|


### Checkout [All Florence Tasks Details @](chainlit.md)


## 🤖 GitHub Actions

This project includes a manual workflow to build and push images to GHCR.
1. Go to **Actions** in your GitHub repo.
2. Select **Build and Push Florence-2 Image**.
3. Click **Run workflow**, choose your hardware (`cpu` or `rocm`), and click the button.


## 📜 Credits & References

This project is built upon the excellent foundation provided by the original MS-Florence2 implementation. Special thanks to the original authors:

[Original implementation](https://github.com/askaresh/MS-Florence2/tree/main/app)