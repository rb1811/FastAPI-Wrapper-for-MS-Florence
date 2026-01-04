import os
import torch
import logging
from PIL import Image
import io
from unittest.mock import patch
from transformers import AutoProcessor, AutoModelForCausalLM, AutoConfig
from transformers.dynamic_module_utils import get_imports

logger = logging.getLogger(__name__)

# --- The "Hugging Face Discussion 13" Workaround ---
def fixed_get_imports(filename: str | os.PathLike) -> list[str]:
    """Workaround for unnecessary flash_attn requirement on CPU/AMD."""
    if not str(filename).endswith("modeling_florence2.py"):
        return get_imports(filename)
    imports = get_imports(filename)
    if "flash_attn" in imports:
        imports.remove("flash_attn")
    return imports
# ----------------------------------------------------

class Florence2Model:
    def __init__(self, config):
        logger.debug("Florence2Model.__init__ called")
        self.device = torch.device("cpu")
        logger.info(f"Using device: {self.device}")

        # Apply the patch while loading the model
        with patch("transformers.dynamic_module_utils.get_imports", fixed_get_imports):
            logger.info("Loading model with flash_attn patch...")
            
            # Load config
            model_config = AutoConfig.from_pretrained(
                config.MODEL_ID, 
                trust_remote_code=True
            )
            model_config.attn_implementation = "sdpa"

            # Load model
            self.model = AutoModelForCausalLM.from_pretrained(
                config.MODEL_ID, 
                config=model_config,
                trust_remote_code=True,
                attn_implementation="sdpa"
            ).to(self.device).eval()
            
            self.processor = AutoProcessor.from_pretrained(
                config.MODEL_ID, 
                trust_remote_code=True
            )
            
        logger.info("Model loaded successfully!")

    def preprocess_image(self, image):
        if not isinstance(image, Image.Image):
            image = Image.open(io.BytesIO(image)).convert('RGB')
        return image

    def run_example(self, task_prompt, text_input=None, image_data=None):
        try:
            image = self.preprocess_image(image_data)
            prompt = task_prompt if text_input is None else task_prompt + text_input
            
            inputs = self.processor(text=prompt, images=image, return_tensors="pt").to(self.device)
            
            generated_ids = self.model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=1024,
                do_sample=False,
                num_beams=3,
            )
            
            generated_text = self.processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
            parsed_answer = self.processor.post_process_generation(
                generated_text,
                task=task_prompt,
                image_size=(image.width, image.height),
            )
            return parsed_answer
        except Exception as e:
            logger.exception(f"Error in run_example: {str(e)}")
            raise