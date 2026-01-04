# Use the local base image
FROM florence-base:latest

WORKDIR /app

# 1. Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 2. Copy and install requirements using uv
# --system tells uv to install into the global site-packages (required for Docker)
COPY requirements.txt .
RUN uv pip install --system --no-cache \
    --index-strategy unsafe-best-match \
    -r requirements.txt

# Copy your app code
COPY . .

# Start Chainlit
CMD ["chainlit", "run", "chainlit_app.py", "--host", "0.0.0.0", "--port", "8010"]