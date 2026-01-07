#!/bin/sh
set -e

INFISICAL_INTERNAL_URL="http://infra-infisical:8080"
echo "🔍 Connecting to Infisical at $INFISICAL_INTERNAL_URL..."

# 1. Authenticate
export INFISICAL_TOKEN=$(infisical login --method=universal-auth \
    --client-id="$INFISICAL_MACHINE_ID" \
    --client-secret="$INFISICAL_MACHINE_SECRET" \
    --domain "$INFISICAL_INTERNAL_URL" \
    --plain --silent)

if [ -z "$INFISICAL_TOKEN" ]; then
    echo "❌ Error: Failed to authenticate with Infisical."
    exit 1
fi

echo "🔐 Identity verified. Initializing Database and starting Florence-2..."



# 2. Fetch and Save to a temporary file
echo "🔓 Fetching secrets from Infisical..."
infisical export --env "dev" --path "/florence" --projectId "$INFISICAL_PROJECT_ID" --domain "$INFISICAL_INTERNAL_URL" --format dotenv-export > /tmp/infisical_vars

# 3. Load variables
. /tmp/infisical_vars

# 4. Execution Logic
if [ "$DEV_MODE" = "true" ]; then
    echo "🛠️ DEV_MODE is ACTIVE. Manual start required."
    echo "👉 Run: . /tmp/infisical_vars && uvicorn main:app --reload --port 8000"
    echo ". /tmp/infisical_vars" >> ~/.bashrc
    tail -f /dev/null
else
    echo "🚀 Starting Production Servers..."
    
    # Start Chainlit in the background
    chainlit run chainlit_app.py --host 0.0.0.0 --port 8010 &
    
    # Start FastAPI as the foreground process (replaces shell via exec)
    # This becomes PID 1
    exec uvicorn fastapi_main:app --host 0.0.0.0 --port 8000
fi