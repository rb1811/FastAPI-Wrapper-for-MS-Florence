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
        # 1. Determine device first
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # 2. Log the ACTUAL device detected
        logger.info("Initializing Florence2Model", 
                    device=str(self.device), 
                    model_id=config.MODEL_ID,
                    cuda_available=torch.cuda.is_available())

        if self.device.type == "cuda":
            logger.info("GPU Hardware Detected", 
                        name=torch.cuda.get_device_name(0),
                        vram=f"{torch.cuda.get_device_properties(self.device).total_memory / 1024**2:.0f}MB")

        try:
            with patch("transformers.dynamic_module_utils.get_imports", fixed_get_imports):
                logger.info("Loading model and processor...", patch="flash_attn_fixed")
                
                model_config = AutoConfig.from_pretrained(
                    config.MODEL_ID, 
                    trust_remote_code=True
                )
                # Ensure we use SDPA for ROCm compatibility
                model_config.attn_implementation = "sdpa"

                self.model = AutoModelForCausalLM.from_pretrained(
                    config.MODEL_ID, 
                    config=model_config,
                    trust_remote_code=True,
                    torch_dtype=torch.float16 if self.device.type == "cuda" else torch.float32 # Use Half precision on GPU
                ).to(self.device).eval()
                
                self.processor = AutoProcessor.from_pretrained(
                    config.MODEL_ID, 
                    trust_remote_code=True
                )
            logger.info("Model loaded successfully ✅")
        except Exception as e:
            logger.exception("Failed to load model", error=str(e))
            raise
    
        # In model.py
    def warmup(self):
        logger.info("🔥 Warming up model with Batch Size 2...")
        # Create a dummy batch of 2 to force kernel compilation for batching
        dummy_input = [
            {"task": "<OD>", "text": None, "image": Image.new('RGB', (224, 224))},
            {"task": "<OD>", "text": None, "image": Image.new('RGB', (224, 224))}
        ]
        # Run it once to "bake" the kernels
        self.run_batch(dummy_input)
        logger.info("✅ Warmup complete.")

    def preprocess_image(self, image_data):
        if not isinstance(image_data, Image.Image):
            image = Image.open(io.BytesIO(image_data)).convert('RGB')
            logger.debug("Image preprocessed from bytes", size=f"{image.width}x{image.height}")
            return image
        return image_data

    def run_example(self, task_prompt, text_input=None, image_data=None):
        """
        Maintains backward compatibility for Chainlit.
        Wraps the batch logic to process a single request.
        """
        results = self.run_batch([
            {"task": task_prompt, "text": text_input, "image": image_data}
        ])
        return results[0]

    def run_batch(self, tasks):
        """
        Core Batching Engine. Handles list of tasks for the Worker.
        Each task is a dict: {'task': str, 'text': str, 'image': bytes}
        """
        if not tasks:
            return []

        start_time = time.time()
        images = []
        prompts = []
        
        try:
            for t in tasks:
                # Use your existing preprocessing logic for consistency
                image = self.preprocess_image(t['image'])
                images.append(image)
                
                prompt = t['task'] if t.get('text') is None else t['task'] + t['text']
                prompts.append(prompt)

            # Determine the correct dtype
            torch_dtype = torch.float16 if self.device.type == "cuda" else torch.float32

            # The "Bus": Processor handles all images and prompts at once
            inputs = self.processor(
                text=prompts, 
                images=images, 
                return_tensors="pt", 
                padding=True
            ).to(self.device, torch_dtype)

            generated_ids = self.model.generate(
                input_ids=inputs["input_ids"],
                pixel_values=inputs["pixel_values"],
                max_new_tokens=1024,
                do_sample=False,
                num_beams=3,
            )

            generated_texts = self.processor.batch_decode(generated_ids, skip_special_tokens=False)
            
            parsed_results = []
            for i, gen_text in enumerate(generated_texts):
                parsed = self.processor.post_process_generation(
                    gen_text,
                    task=tasks[i]['task'],
                    image_size=(images[i].width, images[i].height),
                )
                parsed_results.append(parsed)

            duration = round(time.time() - start_time, 2)
            logger.info("Batch inference complete", 
                        batch_size=len(tasks), 
                        duration_sec=duration)
            
            return parsed_results

        except Exception as e:
            logger.exception("Error during batch model inference", error=str(e))
            raise