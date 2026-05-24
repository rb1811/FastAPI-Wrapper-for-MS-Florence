from pydantic_settings import BaseSettings, SettingsConfigDict
from app.logging_config import get_logger
import os
import chainlit as cl
from datetime import datetime, timedelta
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
                    model_id=self.MODEL_ID, \
                    rate_limit=self.RATE_LIMIT)


class S3StorageClient(BaseStorageClient):
    def __init__(self):
        self.bucket = os.getenv("S3_BUCKET")
        endpoint = os.getenv("S3_ENDPOINT_URL")
        
        logger.info("Initializing S3 Storage Client (SeaweedFS Compatible)", 
                    bucket=self.bucket, 
                    endpoint=endpoint)
        
        try:
            # SeaweedFS uses path-style addressing natively for its S3 emulation layer
            self.client = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=os.getenv("S3_ACCESS_KEY"),
                aws_secret_access_key=os.getenv("S3_SECRET_KEY"),
                use_ssl=False,
                config=boto3.session.Config(signature_version='s3v4')
            )
            logger.info("S3 Client created successfully")
        except Exception as e:
            logger.exception("Failed to initialize S3 client", error=str(e))    

    async def upload_file(self, **kwargs):
        actual_content = kwargs.get("data")
        actual_mime = kwargs.get("mime", "application/octet-stream")
        now = datetime.now().strftime("%Y-%m-%d_%H-%M")
        path_prefix = kwargs.get("path_prefix", "chainlit")

        thread_id = kwargs.get("threadId") or cl.user_session.get("id")
        expiration_time = datetime.utcnow() + timedelta(days=1)
        
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
        clean_key = f"{path_prefix}/{path}/{filename}"

        logger.info("Starting file upload to S3", 
                    key=clean_key, 
                    mime=actual_mime, 
                    size_bytes=len(actual_content) if actual_content else 0)

        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=clean_key,
                Body=actual_content,
                ContentType=actual_mime,
                Expires=expiration_time
            )
            logger.info("✅ Upload successful", s3_path=clean_key)
        except Exception as e:
            logger.exception("S3 upload failed", key=clean_key, error=str(e))
            raise e

        # Updated for SeaweedFS port routing convention
        public_base = os.getenv('S3_PUBLIC_URL', 'http://localhost:8030')
        return {"url": f"{public_base}/buckets/{self.bucket}/{clean_key}"}
    

    async def delete_file(self, filename: str):
        logger.info("Deleting file from S3", key=filename)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=filename)
            logger.info("File deleted successfully", key=filename)
        except Exception as e:
            logger.error("Failed to delete file", key=filename, error=str(e))


    async def get_read_url(self, filename: str):
        # SeaweedFS maps S3 buckets under the '/buckets/' URL path on the Filer API endpoint
        # Keeping signature intact, but pointing directly to the SeaweedFS data route cleanly
        endpoint = os.getenv('S3_ENDPOINT_URL')
        url = f"{endpoint}/buckets/{self.bucket}/{filename}"
        logger.debug("Generated read URL", key=filename, url=url)
        return url
    
    def generate_presigned_url(self, object_key: str, expiration: int = 604800):
        """
        Generates a temporary GET URL for a private S3 object.
        :param object_key: The full path to the file (e.g., 'florence/abc/result.png')
        :param expiration: Time in seconds until the link expires
        """
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket,
                    'Key': object_key
                },
                ExpiresIn=expiration
            )
            
            # Adjusted to swap out your internal Seaweed container name service 
            # with your browser accessible public localhost endpoint.
            internal_host = os.getenv('FLORENCE_S3_SERVICE_NAME', 'florence-s3-seaweedfs')
            public_base = os.getenv('S3_PUBLIC_URL', 'http://localhost:8030')
            
            if internal_host in url:
                url = url.replace(f"http://{internal_host}:8000", public_base)
                # Ensure the path style reflects SeaweedFS buckets structure
                if f"/{self.bucket}/" in url and f"/buckets/{self.bucket}/" not in url:
                    url = url.replace(f"/{self.bucket}/", f"/buckets/{self.bucket}/")
                
            return url
        except Exception as e:
            logger.error("Failed to generate presigned URL", error=str(e))
            return None

    def file_exists(self, object_key: str) -> bool:
        """Checks if an object exists in the S3 bucket."""
        try:
            self.client.head_object(Bucket=self.bucket, Key=object_key)
            return True
        except self.client.exceptions.ClientError as e:
            if e.response['Error']['Code'] == "404":
                return False
            logger.error("Error checking file existence", key=object_key, error=str(e))
            raise e