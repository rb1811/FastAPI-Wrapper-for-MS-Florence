from pydantic_settings import BaseSettings, SettingsConfigDict
from logging_config import get_logger
import os
import chainlit as cl
from datetime import datetime
import boto3
from chainlit.data.storage_clients.base import BaseStorageClient

logger = get_logger(__name__)

class ModelConfig(BaseSettings):
    # Use UPPERCASE to match your .env and your model.py code
    MODEL_ID: str = "microsoft/Florence-2-large"
    RATE_LIMIT: int = 5
    
    # Modern Pydantic v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",            # Ignores CACHE_DIR, etc. so it doesn't crash
        protected_namespaces=(),    # Fixes that "warnings.warn" you saw at the top
        env_prefix=""               # Ensures it looks for the exact name in .env
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.info(f"Loaded ModelConfig: MODEL_ID={self.MODEL_ID}, RATE_LIMIT={self.RATE_LIMIT}")


class S3StorageClient(BaseStorageClient):
    def __init__(self):
        self.bucket = os.getenv("S3_BUCKET")
        self.client = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT_URL"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
            use_ssl=False
        )
    
    async def upload_file(self, **kwargs):
        actual_content = kwargs.get("data")
        actual_mime = kwargs.get("mime", "application/octet-stream")
        now = datetime.now().strftime("%Y-%m-%d_%H-%M")

        # 1. Resolve the ID using your priority list
        thread_id = kwargs.get("threadId") or cl.user_session.get("id")
        
        if not thread_id:
            try:
                thread_id = cl.context.session.thread_id
            except Exception:
                thread_id = None

        # 2. Build the Path: 
        # If thread_id exists: "thread_id/timestamp"
        # If no thread_id: "timestamp" (Fallback)
        path = f"{thread_id}/{now}" if thread_id else now

        # 3. Construct the final key
        original_key = kwargs.get("object_key", "file")
        filename = original_key.split("/")[-1] 
        clean_key = f"florence/{path}/{filename}"

        # 4. Upload to MinIO
        self.client.put_object(
            Bucket=self.bucket,
            Key=clean_key,
            Body=actual_content,
            ContentType=actual_mime
        )
        
        logger.info(f"✅ Uploaded to: {clean_key}")

        # 5. Return the URL for the browser
        public_base = os.getenv('S3_PUBLIC_URL', 'http://localhost:9091')
        return {"url": f"{public_base}/{self.bucket}/{clean_key}"}
    
    async def delete_file(self, filename: str):
        self.client.delete_object(Bucket=self.bucket, Key=filename)

    async def get_read_url(self, filename: str):
        # Simply return the public URL path
        return f"{os.getenv('S3_ENDPOINT_URL')}/{self.bucket}/{filename}"