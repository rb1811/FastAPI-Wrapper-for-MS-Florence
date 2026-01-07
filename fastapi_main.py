import os
import uuid
import structlog
import logfire
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager

from app.logging_config import get_logger, setup_logging, LOGFIRE_ENABLED
from app.config import ModelConfig

# 1. Initialize Logging based on your logging.py logic
setup_logging()
logger = get_logger(__name__)

# 2. Middleware to bind Request IDs to Structured Logs
class StructlogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        structlog.contextvars.clear_contextvars()
        
        # Capture existing ID or generate fresh one
        rid = (
            request.headers.get("x-correlation-id") or 
            request.headers.get("x-request-id") or 
            uuid.uuid4().hex
        )
        
        # Bind rid to all logs within this async context
        structlog.contextvars.bind_contextvars(request_id=rid)
        
        response = await call_next(request)
        # Optional: return rid in headers for debugging
        response.headers["X-Request-ID"] = rid
        return response

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Infisical variables are already loaded via entrypoint.sh
    logger.info("FastAPI Server Starting", service="florence-fastapi")
    yield
    # Shutdown
    logger.info("FastAPI Server Shutting Down")

# 3. Create FastAPI App
app = FastAPI(title="Florence-ai API", lifespan=lifespan)
app.add_middleware(StructlogMiddleware)

# 4. Instrument with Logfire if enabled in your config
if LOGFIRE_ENABLED:
    logfire.instrument_fastapi(app)

@app.get("/health")
async def health():
    return {"status": "healthy", "pid": os.getpid()}

# Example endpoint for Florence inference
@app.post("/predict")
async def predict(data: dict):
    logger.info("Prediction request received", task=data.get("task"))
    return {"message": "Inference endpoint ready"}