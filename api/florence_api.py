import structlog
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query

from app.logging_config import get_logger, setup_logging
from app.constants import TASK_TYPES
from app.config import S3StorageClient, ModelConfig
from app.model import Florence2Model
from app.processing import run_inference_and_visualize
import time

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
    text_input: Optional[str] = Form(None),
    file: UploadFile = File(...)
):
    # A. Fetch the request_id from the middleware's context
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    start_time = time.perf_counter()
    
    logger.info("prediction_start", task=task, filename=file.filename, content_type=file.content_type)
    
    if text_input and (text_input.strip() == "" or text_input.lower() == "string"):
        text_input = None

    if task not in TASK_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid task. Must be one of {TASK_TYPES}")

    try:
        # B. Read input image bytes
        image_bytes = await file.read()
        file_size_kb = len(image_bytes) / 1024
        logger.info("image_read_complete", size_kb=round(file_size_kb, 2))

        # C. MANUALLY STORE INPUT IMAGE
        # Passing threadId=request_id ensures it uses the ID from middleware for the S3 path
        input_upload = await storage_client.upload_file(
            data=image_bytes,
            mime=file.content_type or "image/png",
            object_key=file.filename,
            threadId=request_id 
        )
        logger.info("Input image stored in S3", url=input_upload["url"])
        
        inference_start = time.perf_counter()
        logger.info("inference_engine_start", task=task)

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
        
        inference_duration = time.perf_counter() - inference_start
        logger.info("inference_engine_complete", duration=round(inference_duration, 3), outputs_generated=len(output_urls))

        final_output_urls = []
        for url in output_urls:
            # Extract key: everything after 'florence-uploads/'
            s3_key = url.split(f"{storage_client.bucket}/")[-1]
            presigned = storage_client.generate_presigned_url(s3_key)
            final_output_urls.append(presigned)


        # Do the same for the input image
        input_key = input_upload["url"].split(f"{storage_client.bucket}/")[-1]
        input_presigned = storage_client.generate_presigned_url(input_key)
        
        total_duration = time.perf_counter() - start_time
        logger.info("prediction_request_success", 
                    total_duration=round(total_duration, 3),
                    request_id=request_id)
        
        return {
            "request_id": request_id,
            "task": task,
            "input_image_url": input_presigned,
            "result_data": result,
            "output_visualized_urls": final_output_urls
        }

    except Exception as e:
        logger.exception("Inference endpoint failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@florence_router.get("/tasks", response_model=List[str])
async def get_tasks():
    logger.info("Fetching available task types")
    return TASK_TYPES


@florence_router.get("/refresh-url")
async def refresh_url(url: str = Query(..., description="The S3 URL or object key to refresh")):
    """
    Validates file existence and returns a fresh presigned URL.
    """
    logger.info("Refresh URL request received", url=url)
    
    try:
        # 1. Extract the S3 key from the provided URL
        # Logic: find everything after the bucket name in the URL
        if f"{storage_client.bucket}/" in url:
            s3_key = url.split(f"{storage_client.bucket}/")[-1]
            # Clean up any trailing query parameters if a presigned URL was passed in
            s3_key = s3_key.split('?')[0]
        else:
            # Assume the input was already the key
            s3_key = url

        # 2. Check if the file actually exists in MinIO
        if not storage_client.file_exists(s3_key):
            logger.warning("File not found for refresh", key=s3_key)
            raise HTTPException(status_code=404, detail="File does not exist or has been deleted by lifecycle policy.")

        # 3. Generate a fresh presigned URL (7-day maximum)
        fresh_url = storage_client.generate_presigned_url(s3_key)
        
        return {
            "s3_key": s3_key,
            "presigned_url": fresh_url
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to refresh URL", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error during URL refresh")
