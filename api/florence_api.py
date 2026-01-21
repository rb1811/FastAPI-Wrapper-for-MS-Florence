import structlog
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query
import base64
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


"""
store_image Flag determines whether API should store the images in Blob storage and return the path to the file 
or should return the image bytes 
"""
@florence_router.post("/predict")
async def predict(
    task: str = Form(...),
    text_input: Optional[str] = Form(None),
    file: UploadFile = File(...),
    store_image: bool = Form(True)
):
    try:
        request_id = structlog.contextvars.get_contextvars().get("request_id")
        image_bytes = await file.read()
        
        input_representation = None
        
        # 1. HANDLE INPUT IMAGE
        if store_image:
            # Match the keys expected by S3StorageClient.upload_file (**kwargs)
            input_upload = await storage_client.upload_file(
                data=image_bytes,           # Use 'data', not 'file_bytes'
                mime=file.content_type,     # Use 'mime', not 'mime_type'
                object_key=file.filename,
                threadId=request_id         
            )
            # Get Presigned URL using the URL returned by the upload
            input_key = input_upload["url"].split(f"{storage_client.bucket}/")[-1]
            input_representation = storage_client.generate_presigned_url(input_key)
        else:
            # Convert to Base64 (This part was correct)
            b64_input = base64.b64encode(image_bytes).decode('utf-8')
            input_representation = f"data:{file.content_type};base64,{b64_input}"

        # 2. RUN INFERENCE (Passing store_image to core logic)
        result, output_data = await run_inference_and_visualize(
            model=model,
            task_type=task,
            text_input=text_input,
            image_bytes=image_bytes,
            return_path=store_image, # Maps to the S3 logic in processing.py
            request_id=request_id 
        )

        # 3. HANDLE OUTPUT IMAGES
        final_outputs = []
        for item in output_data:
            if store_image:
                # item is an S3 URL, refresh it to be presigned
                s3_key = item.split(f"{storage_client.bucket}/")[-1].split('?')[0]
                final_outputs.append(storage_client.generate_presigned_url(s3_key))
            else:
                # item is raw bytes, convert to Base64
                b64_output = base64.b64encode(item).decode('utf-8')
                final_outputs.append(f"data:image/png;base64,{b64_output}")

        return {
            "request_id": request_id,
            "task": task,
            "store_image_enabled": store_image,
            "input_image": input_representation,
            "result_data": result,
            "output_visualized": final_outputs 
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
