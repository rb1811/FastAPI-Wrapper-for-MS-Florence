import io
import chainlit as cl
from PIL import Image
from app.logging_config import get_logger
from app.utils import draw_polygons, plot_bbox, draw_ocr_bboxes, fig_to_pil
from app.constants import (
    CAPTION_TO_PHRASE_GROUNDING,
    REFERRING_EXPRESSION_SEGMENTATION,
    OPEN_VOCABULARY_DETECTION,
    OD,
    DENSE_REGION_CAPTION,
    REGION_PROPOSAL,
    REGION_TO_SEGMENTATION,
    OCR_WITH_REGION
)
from app.config import S3StorageClient

logger = get_logger(__name__)

def image_to_bytes(image):
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return buf.getvalue()


async def run_inference_and_visualize(model, task_type, text_input, image_bytes, return_path=False, request_id=None):
    """
    Core logic: Takes task, input, and image bytes. 
    Returns the raw result and a list of processed image data (bytes or MinIO URLs).
    """
    logger.info("Running inference core", task=task_type, return_path=return_path)
    
    # 1. Load Image
    original_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    
    # 2. Inference call
    result = model.run_example(task_type, text_input, image_bytes)
    
    # 2. ADD THE DEBUG LINE HERE
    logger.debug("DEBUGGING MODEL OUTPUT", 
                 task=task_type, 
                 result_type=str(type(result)), 
                 content=result)
    
    # 3. Visualization Logic
    visualized_images = []
    det_tasks = [OD, DENSE_REGION_CAPTION, REGION_PROPOSAL, CAPTION_TO_PHRASE_GROUNDING, OPEN_VOCABULARY_DETECTION]
    
    processed_image = None
    if task_type in det_tasks:
        fig = plot_bbox(original_image, result[task_type])
        processed_image = fig_to_pil(fig)
    elif task_type in [REFERRING_EXPRESSION_SEGMENTATION, REGION_TO_SEGMENTATION]:
        processed_image = original_image.copy()
        draw_polygons(processed_image, result[task_type], fill_mask=True)
    elif task_type == OCR_WITH_REGION:
        processed_image = original_image.copy()
        draw_ocr_bboxes(processed_image, result[task_type])

    # 4. Handle Return Format (Bytes vs. MinIO Path)
    if processed_image:
        img_bytes = image_to_bytes(processed_image)
        
        if return_path:
            # Initialize S3 client and upload
            s3_client = S3StorageClient()
            upload_result = await s3_client.upload_file(
                data=img_bytes, 
                mime="image/png", 
                object_key=f"result_{task_type}.png",
                threadId=request_id
            )
            visualized_images.append(upload_result["url"])
        else:
            visualized_images.append(img_bytes)

    return result, visualized_images


async def process_image_workflow(model, text_input, task_menu_callback):
    """
    Chainlit-specific wrapper. Handles session state and UI updates.
    """
    task_type = cl.user_session.get("task_type")
    image_element = cl.user_session.get("image")
    
    logger.info("Chainlit workflow initiated", task=task_type)
    status_msg = cl.Message(content=f"Processing {task_type}...")
    await status_msg.send()

    try:
        # 1. Read file from disk (Chainlit specific)
        with open(image_element.path, 'rb') as f:
            image_data = f.read()
        
        # 2. FIX: Added 'await' here because the core logic is now async
        result, image_outputs = await run_inference_and_visualize(
            model=model, 
            task_type=task_type, 
            text_input=text_input, 
            image_bytes=image_data,
            return_path=False  # Chainlit usually wants bytes for immediate display
        )
        
        # 3. Format result for Chainlit
        # image_outputs will be a list of bytes because return_path=False
        elements = [
            cl.Image(content=img_bytes, name="result", display="inline") 
            for img_bytes in image_outputs
        ]

        await cl.Message(content=f"**Result for {task_type}:**\n{result}", elements=elements).send()
        logger.info("Chainlit workflow completed ✅", task=task_type)
        
    except Exception as e:
        logger.exception("Error in Chainlit workflow", task=task_type, error=str(e))
        await cl.Message(content=f"Error: {str(e)}").send()
    finally:
        cl.user_session.set("task_type", None)
        cl.user_session.set("image", None)
        await status_msg.remove()
        await task_menu_callback()