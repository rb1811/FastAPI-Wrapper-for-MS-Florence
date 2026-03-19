FROM florence-base:latest
WORKDIR /app

# Accept the argument from docker-compose
ARG DEV_MODE=false

# 1. Standard installs
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Create the unified directory
RUN mkdir -p /app/hf_cache/florence-2-large

# 2. THE DOWNLOAD BLOCK
# This runs during GH Actions (where DEV_MODE is false)
RUN python3 <<EOF
import os
from unittest.mock import patch

# Get the build-arg
dev_mode_env = "${DEV_MODE}".lower()

if dev_mode_env == 'false':
    print("🚀 PROD BUILD: Baking model into /app/hf_cache/florence-2-large...")
    from transformers import AutoProcessor, AutoModelForCausalLM
    from transformers.dynamic_module_utils import get_imports

    def fixed_get_imports(filename):
        imports = get_imports(filename)
        if 'flash_attn' in imports:
            imports.remove('flash_attn')
        return imports

    model_id = 'microsoft/Florence-2-large'
    save_path = '/app/hf_cache/florence-2-large'

    with patch('transformers.dynamic_module_utils.get_imports', fixed_get_imports):
        p = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        m = AutoModelForCausalLM.from_pretrained(model_id, trust_remote_code=True)
        p.save_pretrained(save_path)
        m.save_pretrained(save_path)
else:
    print("🛠️ DEV_MODE ACTIVE: Skipping internal download. Local mount will be used.")
EOF

# 3. Final steps
COPY . .

# Unified Model ID for everyone
ENV MODEL_ID="/app/hf_cache/florence-2-large"

RUN chmod +x entrypoint.sh 
ENTRYPOINT ["/bin/sh", "./entrypoint.sh"]