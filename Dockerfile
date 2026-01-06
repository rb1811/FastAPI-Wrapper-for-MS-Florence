# Use the local base image
FROM florence-base:latest

WORKDIR /app

# 1. Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 2. Install Python requirements
COPY requirements.txt .
# We add the index-strategy flag here to handle the multiple indexes in your requirements.txt
RUN uv pip install --system --no-cache \
    --index-strategy unsafe-best-match \
    -r requirements.txt

# 3. Copy app code and entrypoint
COPY . .
RUN chmod +x entrypoint.sh 

ENTRYPOINT ["/bin/sh", "./entrypoint.sh"]