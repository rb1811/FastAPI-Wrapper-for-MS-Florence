FROM florence-base:latest
WORKDIR /app

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# 2. Copy application code
COPY app/ ./app/
COPY api/ ./api/
COPY entrypoint.sh download_model.sh ./
COPY fastapi_main.py chainlit_app.py ./

# 3. Model path configuration
ENV MODEL_ID="/app/hf_cache/florence-2-large"

# 4. Entrypoint
RUN chmod +x entrypoint.sh download_model.sh
ENTRYPOINT ["/bin/sh", "./entrypoint.sh"]