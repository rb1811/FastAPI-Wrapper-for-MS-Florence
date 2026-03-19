import os
import redis
import json
import uuid
import base64
import structlog
from fastapi import HTTPException
from app.logging_config import get_logger

logger = get_logger(__name__)

r = redis.from_url(os.environ.get("REDIS_HOST", "redis://infra-redis:6379"))

class RedisModelProxy:
    """
    Acts as a 'Fake' model. Instead of running inference, 
    it pushes to Redis and waits for the worker.
    """
    def run_example(self, task_prompt, text_input=None, image_data=None):
        # image_data is mandatory as per API contract
        if image_data is None:
            raise ValueError("image_data is mandatory for inference")

        # Get existing request_id from context or create one
        request_id = structlog.contextvars.get_contextvars().get("request_id") or uuid.uuid4().hex
        
        logger.info(f"📡 Dispatching task to worker task. request_id {request_id} ")

        # 1. Package the task
        payload = {
            "request_id": request_id,
            "task": task_prompt,
            "text_input": text_input,
            "image_b64": base64.b64encode(image_data).decode('utf-8')
        }

        # 2. Push to the general outbox
        r.lpush("florence_tasks", json.dumps(payload))

        # 3. Blocking Wait on the private mailbox (request_id)
        # Timeout is 30 seconds
        res = r.brpop(request_id, timeout=60)

        if not res:
            logger.error(f"⏰ Worker response timeout request_id {request_id}")
            raise HTTPException(status_code=504, detail="Model worker timeout. The queue might be too long.")

        # res is a tuple: (key_name, value)
        _, result_json = res
        return json.loads(result_json)