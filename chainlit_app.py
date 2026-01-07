import os
import chainlit as cl
from app.model import Florence2Model
from app.config import ModelConfig, S3StorageClient
from app.constants import (
    TASK_TYPES,
    CAPTION_TO_PHRASE_GROUNDING,
    REFERRING_EXPRESSION_SEGMENTATION,
    OPEN_VOCABULARY_DETECTION
)
from app.logging_config import get_logger
from app.processing import process_image_workflow
from app.database import get_data_layer # Import the new factory

from chainlit.context import local_steps
def fix_context():
    try:
        local_steps.get()
    except LookupError:
        local_steps.set([])

logger = get_logger(__name__)
model = Florence2Model(ModelConfig())
storage_client = S3StorageClient()

@cl.data_layer
def setup_data_layer():
    # Pass the storage client to the database helper
    return get_data_layer(storage_client)

async def send_task_menu():
    fix_context()
    actions = [cl.Action(name="select_task", payload={"task": t}, label=t) for t in TASK_TYPES]
    await cl.Message(content="### Florence-2 Menu\nSelect a task:", actions=actions).send()

@cl.on_chat_start
async def start():
    logger.info("New session started", session_id=cl.user_session.get("id"))
    cl.user_session.set("storage_client", storage_client)
    await send_task_menu()

@cl.action_callback("select_task")
async def on_action(action: cl.Action):
    fix_context()
    task_type = action.payload.get("task")
    logger.info("Task selected", task=task_type)
    cl.user_session.set("task_type", task_type)
    cl.user_session.set("image", None)
    await cl.Message(content=f"✅ Task set to `{task_type}`. Please upload your image.").send()
    await action.remove()

@cl.on_message
async def handle_message(message: cl.Message):
    fix_context()
    msg_content = message.content.strip()

    if msg_content.lower() == "menu":
        await send_task_menu()
        return

    if msg_content in TASK_TYPES:
        cl.user_session.set("task_type", msg_content)
        await cl.Message(content=f"✅ Task set to `{msg_content}`. Please upload your image.").send()
        return

    task_type = cl.user_session.get("task_type")
    if not task_type:
        await cl.Message(content="Please select a task from the menu above.").send()
        return

    image_element = next((elem for elem in message.elements if "image" in elem.mime), None)

    if image_element:
        cl.user_session.set("image", image_element)
        grounding_tasks = [CAPTION_TO_PHRASE_GROUNDING, REFERRING_EXPRESSION_SEGMENTATION, OPEN_VOCABULARY_DETECTION]
        if task_type in grounding_tasks and not msg_content:
            await cl.Message(content=f"Task `{task_type}` requires a text prompt.").send()
            return
        await process_image_workflow(model, msg_content, send_task_menu)
    else:
        if cl.user_session.get("image"):
            await process_image_workflow(model, msg_content, send_task_menu)
        else:
            await cl.Message(content="Please upload an image.").send()

if __name__ == "__main__":
    cl.run()