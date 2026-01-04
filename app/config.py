from pydantic_settings import BaseSettings, SettingsConfigDict
from logging_config import get_logger

logger = get_logger(__name__)

class ModelConfig(BaseSettings):
    # Use UPPERCASE to match your .env and your model.py code
    MODEL_ID: str = "microsoft/Florence-2-large"
    RATE_LIMIT: int = 5
    
    # Modern Pydantic v2 configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",            # Ignores CACHE_DIR, etc. so it doesn't crash
        protected_namespaces=(),    # Fixes that "warnings.warn" you saw at the top
        env_prefix=""               # Ensures it looks for the exact name in .env
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.info(f"Loaded ModelConfig: MODEL_ID={self.MODEL_ID}, RATE_LIMIT={self.RATE_LIMIT}")