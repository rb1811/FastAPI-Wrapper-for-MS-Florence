# Use your updated local base image
FROM florence-base:latest

WORKDIR /app

# 1. Copy requirements (uv is already in /bin/ from the base image)
COPY requirements.txt .

# 2. Install requirements using uv
# We use --system because we are inside a dedicated container
RUN uv pip install --system --no-cache \
    --index-strategy unsafe-best-match \
    -r requirements.txt

# 3. Copy the heavy model
COPY hf_cache/florence-2-large /app/hf_cache/florence-2-large
    
# 4. Copy app code and entrypoint
COPY . .

# Ensure the environment variable points to this internal path
ENV MODEL_ID="/app/hf_cache/florence-2-large"

RUN chmod +x entrypoint.sh 

ENTRYPOINT ["/bin/sh", "./entrypoint.sh"]