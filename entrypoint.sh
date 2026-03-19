#!/bin/sh
set -e

echo "Current Model Path (MODEL_ID): $MODEL_ID"

wait_for_worker() {
    local log_file="/tmp/model_worker.log"
    local timeout=60
    local elapsed=0
    
    echo "[WAIT] Monitoring GPU Warmup..."

    while [ "$elapsed" -lt "$timeout" ]; do
        if ! pgrep -f "app.model_worker" > /dev/null; then
            echo "CRITICAL: Model Worker died!"
            exit 1
        fi

        if grep -q "Warmup complete" "$log_file" 2>/dev/null; then
            echo "SUCCESS: Model is ready."
            # CLEANUP: We don't need this temp file anymore
            rm -f "$log_file"
            return 0
        fi

        echo " Still warming up... (${elapsed}s/60s)"
        sleep 5
        elapsed=`expr $elapsed + 5`
    done

    echo "ERROR: Warmup timed out."
    exit 1
}


INFISICAL_INTERNAL_URL="http://infra-infisical:8080"
echo "Connecting to Infisical at $INFISICAL_INTERNAL_URL..."

# 1. Authenticate
export INFISICAL_TOKEN=$(infisical login --method=universal-auth \
    --client-id="$INFISICAL_MACHINE_ID" \
    --client-secret="$INFISICAL_MACHINE_SECRET" \
    --domain "$INFISICAL_INTERNAL_URL" \
    --plain --silent)

if [ -z "$INFISICAL_TOKEN" ]; then
    echo "Error: Failed to authenticate with Infisical."
    exit 1
fi

echo "Identity verified. Initializing Database and starting Florence-2..."

# 2. Fetch and Save to a temporary file
echo "Fetching secrets from Infisical..."
infisical export --env "dev" --path "/florence" --projectId "$INFISICAL_PROJECT_ID" --domain "$INFISICAL_INTERNAL_URL" --format dotenv-export > /tmp/infisical_vars

# 3. Load variables
. /tmp/infisical_vars

echo "🧠 Starting Single Model Worker (The Brain)..."
export PYTHONPATH=$PYTHONPATH:.
rm -f /tmp/model_worker.log
touch /tmp/model_worker.log
python3 -u -m app.model_worker 2>&1 | tee /tmp/model_worker.log &
sleep 2
wait_for_worker

# 4. Execution Logic
if [ "$DEV_MODE" = "true" ]; then
    echo "🛠️ DEV_MODE is ACTIVE. Manual start required."
    echo "👉 Run: . /tmp/infisical_vars && uvicorn main:app --reload --port 8000"
    echo ". /tmp/infisical_vars" >> ~/.bashrc
    tail -f /dev/null
else
    echo "🚀 Starting Production Servers..."
    
    SHOULD_START_API=true
    SHOULD_START_CHAT=true
    API_WORKER_COUNT=${API_WORKER_COUNT:-2}

    if [ -n "$DISABLE_FLORENCE_API" ]; then
        echo "🚫 API Service is DISABLED via environment flag."
        SHOULD_START_API=false
    fi

    if [ -n "$DISABLE_FLORENCE_CHAT" ]; then
        echo "🚫 Chat Service is DISABLED via environment flag."
        SHOULD_START_CHAT=false
    fi

    # Start Services
    if [ "$SHOULD_START_API" = true ] && [ "$SHOULD_START_CHAT" = true ]; then
        echo "Starting BOTH API and Chat..."
        chainlit run chainlit_app.py --port 8010 --host 0.0.0.0 > /dev/stdout 2>&1 & 
        exec gunicorn fastapi_main:app --workers $API_WORKER_COUNT --worker-class uvicorn.workers.UvicornWorker --timeout 120 --bind 0.0.0.0:8000
    
    elif [ "$SHOULD_START_API" = true ]; then
        echo "Starting API ONLY..."
        exec gunicorn fastapi_main:app --workers $API_WORKER_COUNT --worker-class uvicorn.workers.UvicornWorker --timeout 120 --bind 0.0.0.0:8000
        
    elif [ "$SHOULD_START_CHAT" = true ]; then
        echo "Starting Chat ONLY..."
        chainlit run chainlit_app.py --port 8010 --host 0.0.0.0
        
    else
        echo "⚠️ ERROR: Both services are disabled. Container has nothing to do."
        exit 1
    fi
fi