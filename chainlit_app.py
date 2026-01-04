import chainlit as cl
from app.model import Florence2Model
from app.config import ModelConfig
from logging_config import get_logger
import io
from PIL import Image
from app.utils import draw_polygons, plot_bbox, draw_ocr_bboxes, fig_to_pil

# --- CRITICAL FIX FOR LOOKUPERROR ---
from chainlit.context import local_steps
def fix_context():
    try:
        local_steps.get()
    except LookupError:
        local_steps.set([])
# ------------------------------------

logger = get_logger(__name__)
model = Florence2Model(ModelConfig())

# Dictionary containing tokens and their friendly descriptions
TASK_DESCRIPTIONS = {
    "<CAPTION>": "Generates a simple caption for the image.",
    "<DETAILED_CAPTION>": "Provides a detailed description of the image.",
    "<MORE_DETAILED_CAPTION>": "Generates a very comprehensive description of the image.",
    "<OBJECT_DETECTION>": "Detects and locates objects within the image.",
    "<OD>": "Short for Object Detection; locates main objects.",
    "<OCR>": "Performs Optical Character Recognition (Text extraction).",
    "<OCR_WITH_REGION>": "OCR on specific regions of the image with locations.",
    "<CAPTION_TO_PHRASE_GROUNDING>": "Locates specific phrases or objects mentioned in a caption.",
    "<DENSE_REGION_CAPTION>": "Generates captions for many specific regions in the image.",
    "<REGION_PROPOSAL>": "Suggests regions of interest without specific labels.",
    "<REFERRING_EXPRESSION_SEGMENTATION>": "Segments the image based on a specific text description.",
    "<REGION_TO_SEGMENTATION>": "Generates a segmentation mask for a specified box/region.",
    "<OPEN_VOCABULARY_DETECTION>": "Detects objects based on any category you type.",
    "<REGION_TO_CATEGORY>": "Classifies a specific region into a category.",
    "<REGION_TO_DESCRIPTION>": "Generates a detailed description for a specific region."
}

TASK_TYPES = list(TASK_DESCRIPTIONS.keys())

async def send_task_menu():
    fix_context()
    actions = [
        cl.Action(name="select_task", payload={"task": task}, label=task) 
        for task in TASK_TYPES
    ]
    
    await cl.Message(
        content="**Florence-2 Menu**\nSelect a task or type 'list' for descriptions:",
        actions=actions
    ).send()

@cl.on_chat_start
async def start():
    await send_task_menu()

@cl.action_callback("select_task")
async def on_action(action: cl.Action):
    fix_context()
    task_type = action.payload.get("task")
    cl.user_session.set("task_type", task_type)
    await cl.Message(content=f"✅ Task set to `{task_type}`. Now, please upload your image.").send()
    await action.remove()

@cl.on_message
async def handle_message(message: cl.Message):
    fix_context()
    msg_content = message.content.strip()

    # Enhanced "list" command with descriptions
    if msg_content.lower() == "list":
        list_msg = "**Available Florence-2 Tasks:**\n\n"
        for token, desc in TASK_DESCRIPTIONS.items():
            # Using code blocks for tokens to enable one-click copy
            list_msg += f"```text\n{token}\n```\n* {desc}\n---\n"
        
        await cl.Message(content=list_msg).send()
        return

    if msg_content.lower() == "menu":
        await send_task_menu()
        return

    # Direct token input support
    if msg_content in TASK_TYPES:
        cl.user_session.set("task_type", msg_content)
        await cl.Message(content=f"✅ Task set to `{msg_content}`. Please upload your image.").send()
        return

    task_type = cl.user_session.get("task_type")
    
    if not task_type:
        await cl.Message(content="Please select a task from the menu or type a token (e.g. `<OD>`).").send()
        return

    image_element = next((elem for elem in message.elements if "image" in elem.mime), None)

    if image_element:
        cl.user_session.set("image", image_element)
        grounding_tasks = ["<CAPTION_TO_PHRASE_GROUNDING>", "<REFERRING_EXPRESSION_SEGMENTATION>", "<OPEN_VOCABULARY_DETECTION>"]
        if task_type in grounding_tasks and not msg_content:
            await cl.Message(content=f"Task `{task_type}` requires a text prompt. What should I find?").send()
            return
        else:
            await process_image(msg_content)
    else:
        if cl.user_session.get("image"):
            await process_image(msg_content)
        else:
            await cl.Message(content="Task is set. Please upload an image.").send()

async def process_image(text_input):
    task_type = cl.user_session.get("task_type")
    image_element = cl.user_session.get("image")
    
    status_msg = cl.Message(content=f"Processing {task_type}...")
    await status_msg.send()

    try:
        with open(image_element.path, 'rb') as f:
            image_data = f.read()
        
        original_image = Image.open(image_element.path).convert("RGB")
        result = model.run_example(task_type, text_input, image_data)
        
        elements = []
        # Detection Visualization (mapping both <OD> and <OBJECT_DETECTION>)
        det_tasks = ["<OD>", "<OBJECT_DETECTION>", "<DENSE_REGION_CAPTION>", "<REGION_PROPOSAL>", "<CAPTION_TO_PHRASE_GROUNDING>", "<OPEN_VOCABULARY_DETECTION>"]
        if task_type in det_tasks:
            fig = plot_bbox(original_image, result[task_type])
            elements.append(cl.Image(content=image_to_bytes(fig_to_pil(fig)), name="result", display="inline"))
            
        elif task_type in ["<REFERRING_EXPRESSION_SEGMENTATION>", "<REGION_TO_SEGMENTATION>"]:
            output_image = original_image.copy()
            draw_polygons(output_image, result[task_type], fill_mask=True)
            elements.append(cl.Image(content=image_to_bytes(output_image), name="result", display="inline"))
            
        elif task_type == "<OCR_WITH_REGION>":
            output_image = original_image.copy()
            draw_ocr_bboxes(output_image, result[task_type])
            elements.append(cl.Image(content=image_to_bytes(output_image), name="result", display="inline"))

        await cl.Message(content=f"**Result for {task_type}:**\n{result}", elements=elements).send()
        
    except Exception as e:
        logger.exception("Inference error")
        await cl.Message(content=f"Error: {str(e)}").send()
    finally:
        cl.user_session.set("task_type", None)
        cl.user_session.set("image", None)
        await status_msg.remove()
        await send_task_menu()

def image_to_bytes(image):
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return buf.getvalue()

if __name__ == "__main__":
    cl.run()