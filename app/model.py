import os
import torch
from PIL import Image
import io
import time
from unittest.mock import patch
from transformers import AutoProcessor, AutoModelForCausalLM, AutoConfig
from transformers.dynamic_module_utils import get_imports
from app.logging_config import get_logger

# Use the structured logger
logger = get_logger(__name__)

def fixed_get_imports(filename: str | os.PathLike) -> list[str]:
    """Workaround for unnecessary flash_attn requirement on CPU/AMD."""
    if not str(filename).endswith("modeling_florence2.py"):
        return get_imports(filename)
    imports = get_imports(filename)
    if "flash_attn" in imports:
        imports.remove("flash_attn")
    return imports

class Florence2Model:
    def __init__(self, config):
        logger.info("Initializing Florence2Model", device="cpu", model_id=config.MODEL_ID)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        try:
            with patch("transformers.dynamic_module_utils.get_imports", fixed_get_imports):
                logger.info("Loading model and processor...", patch="flash_attn_fixed")
                
                model_config = AutoConfig.from_pretrained(
                    config.MODEL_ID, 
                    trust_remote_code=True
                )
                model_config.attn_implementation = "sdpa"

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
            logger.info("Model loaded successfully ✅")
        except Exception as e:
            logger.exception("Failed to load model", error=str(e))
            raise

    def preprocess_image(self, image_data):
        if not isinstance(image_data, Image.Image):
            image = Image.open(io.BytesIO(image_data)).convert('RGB')
            logger.debug("Image preprocessed from bytes", size=f"{image.width}x{image.height}")
            return image
        return image_data

    def run_example(self, task_prompt, text_input=None, image_data=None):
        start_time = time.time()
        logger.info("Starting inference", task=task_prompt)
        
        try:
            image = self.preprocess_image(image_data)
            prompt = task_prompt if text_input is None else task_prompt + text_input
            
            # Log structured metadata about the request
            logger.debug("Processing tokens", 
                         task=task_prompt, 
                         has_text_input=bool(text_input),
                         img_dims=f"{image.width}x{image.height}")

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
            
            duration = round(time.time() - start_time, 2)
            logger.info("Inference complete", 
                        duration_sec=duration, 
                        task=task_prompt)
            
            return parsed_answer

        except Exception as e:
            logger.exception("Error during model inference", 
                             task=task_prompt, 
                             error=str(e))
            raise