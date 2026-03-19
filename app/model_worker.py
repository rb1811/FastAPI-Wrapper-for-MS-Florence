import os
import redis
import json
import base64
import time
from app.model import Florence2Model
from app.config import ModelConfig
from app.logging_config import get_logger, setup_logging


# Initialize structured logger
setup_logging()
logger = get_logger("model_worker")

# --- CONFIGURATION ---
# Read limits from environment (Infisical/Docker)
REDIS_HOST = os.environ.get("REDIS_HOST") # Use the full URL if possible
MAX_BATCH_SIZE = int(os.environ.get("API_WORKER_COUNT", "4")) # batch size is same as no. of fastapi instances running 
# This is how long we wait for the 'bus' to fill up before leaving the station
BATCH_TIMEOUT_MS = float(os.environ.get("BATCH_TIMEOUT_MS", "200")) / 1000 

try:
    if not REDIS_HOST:
        raise ValueError("REDIS_HOST is required")

    r = redis.from_url(REDIS_HOST)
    model = Florence2Model(ModelConfig())
    model.warmup()
    logger.info("Model Worker Online", 
                device=str(model.device), 
                max_batch_size=MAX_BATCH_SIZE,
                batch_timeout=f"{BATCH_TIMEOUT_MS*1000}ms")
except Exception as e:
    logger.exception("Failed to initialize Model Worker", error=str(e))
    exit(1)


while True:
    try:
        # 1. Wait for the FIRST task (Blocking)
        res = r.brpop("florence_tasks", timeout=1)
        if not res:
            continue
            
        _, first_task_raw = res
        task_list = [json.loads(first_task_raw)]
        
        # 2. DYNAMIC BATCHING: Try to fill the bus
        # We wait up to BATCH_TIMEOUT_MS to see if more tasks arrive
        deadline = time.time() + BATCH_TIMEOUT_MS
        
        while len(task_list) < MAX_BATCH_SIZE and time.time() < deadline:
            # Non-blocking pop
            next_task_raw = r.rpop("florence_tasks")
            if next_task_raw:
                task_list.append(json.loads(next_task_raw))
            else:
                # Small sleep to prevent tight loop if queue is empty
                time.sleep(0.01)

        if len(task_list) > 1:
            logger.info("Batch assembled", 
                        count=len(task_list),
                        ids=[t.get('request_id') for t in task_list])

        # 3. Prepare images for run_batch
        batch_input = []
        for t in task_list:
            # Check for required fields to avoid crash
            if 'image_b64' not in t:
                logger.error("Malformed task: missing image_b64", request_id=t.get('request_id'))
                continue
                
            batch_input.append({
                "task": t['task'],
                "text": t.get('text_input'),
                "image": base64.b64decode(t['image_b64'])
            })

        # 4. Run Inference
        inference_start = time.time()
        results = model.run_batch(batch_input)
        duration = round(time.time() - inference_start, 2)

        # 5. Delivery
        for i, result in enumerate(results):
            req_id = task_list[i]['request_id']
            
            # Push to the "Private Mailbox"
            r.lpush(req_id, json.dumps(result))
            r.expire(req_id, 60) # TTL for safety
            
            logger.info("Delivered", 
                        request_id=req_id, 
                        duration=duration, 
                        batch_pos=i)

    except Exception as e:
        logger.exception("Worker loop error", error=str(e))
        time.sleep(1)