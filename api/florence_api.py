import structlog
from typing import List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from app.logging_config import get_logger, setup_logging
from app.constants import TASK_TYPES
from app.config import S3StorageClient, ModelConfig
from app.model import Florence2Model
from app.processing import run_inference_and_visualize

# 1. Initialize Logging and Global Clients
setup_logging()
logger = get_logger(__name__)
storage_client = S3StorageClient()
# Ideally, the model is initialized once at the app level/lifespan
model = Florence2Model(ModelConfig()) 

florence_router = APIRouter(tags=["Run Florence LLM"])

@florence_router.post("/predict")
async def predict(
    task: str = Form(...),
    text_input: str = Form(None),
    file: UploadFile = File(...)
):
    # A. Fetch the request_id from the middleware's context
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    logger.info("Prediction request received", task=task, request_id=request_id)

    if task not in TASK_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid task. Must be one of {TASK_TYPES}")

    try:
        # B. Read input image bytes
        image_bytes = await file.read()

        # C. MANUALLY STORE INPUT IMAGE
        # Passing threadId=request_id ensures it uses the ID from middleware for the S3 path
        input_upload = await storage_client.upload_file(
            data=image_bytes,
            mime=file.content_type or "image/png",
            object_key=file.filename,
            threadId=request_id 
        )
        logger.info("Input image stored in S3", url=input_upload["url"])

        # D. RUN INFERENCE & STORE RESULT
        # Setting return_path=True tells the core logic to upload the result to S3
        # We need to ensure run_inference_and_visualize passes the request_id down
        result, output_urls = await run_inference_and_visualize(
            model=model,
            task_type=task,
            text_input=text_input,
            image_bytes=image_bytes,
            return_path=True,
            request_id=request_id # Pass this to ensure result is in same folder
        )

        return {
            "request_id": request_id,
            "task": task,
            "input_image_url": input_upload["url"],
            "result_data": result,
            "output_visualized_urls": output_urls
        }

    except Exception as e:
        logger.exception("Inference endpoint failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@florence_router.get("/tasks", response_model=List[str])
async def get_tasks():
    logger.info("Fetching available task types")
    return TASK_TYPES
