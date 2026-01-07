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
    OBJECT_DETECTION,
    DENSE_REGION_CAPTION,
    REGION_PROPOSAL,
    REGION_TO_SEGMENTATION,
    OCR_WITH_REGION
)

logger = get_logger(__name__)

def image_to_bytes(image):
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return buf.getvalue()

async def process_image_workflow(model, text_input, task_menu_callback):
    """Handles the model inference and result visualization."""
    task_type = cl.user_session.get("task_type")
    image_element = cl.user_session.get("image")
    
    logger.info("Processing workflow initiated", task=task_type, has_text_input=bool(text_input))
    status_msg = cl.Message(content=f"Processing {task_type}...")
    await status_msg.send()

    try:
        with open(image_element.path, 'rb') as f:
            image_data = f.read()
        
        original_image = Image.open(image_element.path).convert("RGB")
        
        # Inference call using the model instance passed from the app
        result = model.run_example(task_type, text_input, image_data)
        
        elements = []
        det_tasks = [OD, OBJECT_DETECTION, DENSE_REGION_CAPTION, REGION_PROPOSAL, CAPTION_TO_PHRASE_GROUNDING, OPEN_VOCABULARY_DETECTION]
        
        if task_type in det_tasks:
            logger.debug("Visualizing detection results", task=task_type)
            fig = plot_bbox(original_image, result[task_type])
            elements.append(cl.Image(content=image_to_bytes(fig_to_pil(fig)), name="result", display="inline"))
        elif task_type in [REFERRING_EXPRESSION_SEGMENTATION, REGION_TO_SEGMENTATION]:
            logger.debug("Visualizing segmentation results", task=task_type)
            output_image = original_image.copy()
            draw_polygons(output_image, result[task_type], fill_mask=True)
            elements.append(cl.Image(content=image_to_bytes(output_image), name="result", display="inline"))
        elif task_type == OCR_WITH_REGION:
            logger.debug("Visualizing OCR results", task=task_type)
            output_image = original_image.copy()
            draw_ocr_bboxes(output_image, result[task_type])
            elements.append(cl.Image(content=image_to_bytes(output_image), name="result", display="inline"))

        await cl.Message(content=f"**Result for {task_type}:**\n{result}", elements=elements).send()
        logger.info("Processing workflow completed successfully ✅", task=task_type)
        
    except Exception as e:
        logger.exception("Error in processing workflow", task=task_type, error=str(e))
        await cl.Message(content=f"Error: {str(e)}").send()
    finally:
        # Reset session state for next interaction
        cl.user_session.set("task_type", None)
        cl.user_session.set("image", None)
        await status_msg.remove()
        # Trigger the menu callback passed from the main app
        await task_menu_callback()