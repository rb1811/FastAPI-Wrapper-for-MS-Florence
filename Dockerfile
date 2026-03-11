FROM florence-base:latest
WORKDIR /app

# Accept the argument from docker-compose
ARG DEV_MODE=false

# 1. Standard installs
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt
RUN mkdir -p /app/model_weights

# 2. THE DOWNLOAD BLOCK
# We move the "if" logic into Python so Docker doesn't get confused by shell syntax
RUN python3 <<EOF
import os
from unittest.mock import patch

# Only run the download if DEV_MODE is false
dev_mode_env = os.environ.get('DEV_MODE', '${DEV_MODE}').lower()
if dev_mode_env == 'false':
    print("PROD DETECTED: Baking model into image...")
    from transformers import AutoProcessor, AutoModelForCausalLM
    from transformers.dynamic_module_utils import get_imports

    def fixed_get_imports(filename):
        imports = get_imports(filename)
        if 'flash_attn' in imports:
            imports.remove('flash_attn')
        return imports

    model_id = 'microsoft/Florence-2-large'
    save_path = '/app/model_weights'

    with patch('transformers.dynamic_module_utils.get_imports', fixed_get_imports):
        p = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        m = AutoModelForCausalLM.from_pretrained(model_id, trust_remote_code=True)
        p.save_pretrained(save_path)
        m.save_pretrained(save_path)
else:
    print("DEV_MODE ACTIVE: Skipping internal download.")
EOF

# 3. Final steps
COPY . .

# Environment path switching
ENV MODEL_ID=${DEV_MODE:+"/app/hf_cache/florence-2-large"}
ENV MODEL_ID=${MODEL_ID:-"/app/model_weights"}

RUN chmod +x entrypoint.sh 
ENTRYPOINT ["/bin/sh", "./entrypoint.sh"]