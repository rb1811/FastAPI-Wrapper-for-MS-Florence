from pydantic_settings import BaseSettings, SettingsConfigDict
from app.logging_config import get_logger
import os
import chainlit as cl
from datetime import datetime
import boto3
from chainlit.data.storage_clients.base import BaseStorageClient

# Initializing the structured logger
logger = get_logger(__name__)

class ModelConfig(BaseSettings):
    MODEL_ID: str = "microsoft/Florence-2-large"
    RATE_LIMIT: int = 5
    
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        protected_namespaces=(),
        env_prefix=""
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Structured log with model details as metadata
        logger.info("Model configuration initialized", 
                    model_id=self.MODEL_ID, 
                    rate_limit=self.RATE_LIMIT)


class S3StorageClient(BaseStorageClient):
    def __init__(self):
        self.bucket = os.getenv("S3_BUCKET")
        endpoint = os.getenv("S3_ENDPOINT_URL")
        
        logger.info("Initializing S3 Storage Client", 
                    bucket=self.bucket, 
                    endpoint=endpoint)
        
        try:
            self.client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
                aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
                use_ssl=False
            )
            logger.info("S3 Client created successfully")
        except Exception as e:
            logger.exception("Failed to initialize S3 client", error=str(e))

    async def upload_file(self, **kwargs):
        actual_content = kwargs.get("data")
        actual_mime = kwargs.get("mime", "application/octet-stream")
        now = datetime.now().strftime("%Y-%m-%d_%H-%M")

        thread_id = kwargs.get("threadId") or cl.user_session.get("id")
        
        if not thread_id:
            try:
                thread_id = cl.context.session.thread_id
                logger.debug("Fetched thread_id from context", thread_id=thread_id)
            except Exception:
                logger.warning("Could not resolve thread_id for upload fallback used")
                thread_id = None

        path = f"{thread_id}/{now}" if thread_id else now
        original_key = kwargs.get("object_key", "file")
        filename = original_key.split("/")[-1] 
        clean_key = f"florence/{path}/{filename}"

        logger.info("Starting file upload to S3", 
                    key=clean_key, 
                    mime=actual_mime, 
                    size_bytes=len(actual_content) if actual_content else 0)

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=clean_key,
                Body=actual_content,
                ContentType=actual_mime
            )
            logger.info("✅ Upload successful", s3_path=clean_key)
        except Exception as e:
            logger.exception("S3 upload failed", key=clean_key, error=str(e))
            raise e

        public_base = os.getenv('S3_PUBLIC_URL', 'http://localhost:9091')
        return {"url": f"{public_base}/{self.bucket}/{clean_key}"}
    
    async def delete_file(self, filename: str):
        logger.info("Deleting file from S3", key=filename)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=filename)
            logger.info("File deleted successfully", key=filename)
        except Exception as e:
            logger.error("Failed to delete file", key=filename, error=str(e))

    async def get_read_url(self, filename: str):
        url = f"{os.getenv('S3_ENDPOINT_URL')}/{self.bucket}/{filename}"
        logger.debug("Generated read URL", key=filename, url=url)
        return url