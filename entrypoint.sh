#!/bin/sh
set -e

# Define the stable internal address for Infisical
INFISICAL_INTERNAL_URL="http://infra-infisical:8080"

echo "🔍 Connecting to Infisical at $INFISICAL_INTERNAL_URL..."

# 1. Authenticate using Machine Identity
# These variables should be passed into the container via docker-compose from your .env
export INFISICAL_TOKEN=$(infisical login --method=universal-auth \
    --client-id="$INFISICAL_MACHINE_ID" \
    --client-secret="$INFISICAL_MACHINE_SECRET" \
    --domain "$INFISICAL_INTERNAL_URL" \
    --plain --silent)

if [ -z "$INFISICAL_TOKEN" ]; then
    echo "❌ Error: Failed to authenticate with Infisical. Check your Client ID and Secret."
    exit 1
fi

echo "🔐 Identity verified. Initializing Database and starting Florence-2..."



# 2. Fetch and Save to a temporary file
echo "🔓 Fetching secrets from Infisical..."
# We save to /tmp/infisical_vars so it survives as long as the container is up
infisical export --env "dev" --path "/florence" --projectId "$INFISICAL_PROJECT_ID" --domain "$INFISICAL_INTERNAL_URL" --format dotenv-export > /tmp/infisical_vars

# 3. Load them into the current script session
. /tmp/infisical_vars

# 4. Standard If/Else Logic
if [ "$DEV_MODE" = "true" ]; then
    echo "🛠️ DEV_MODE is ACTIVE."
    echo "👉 To see variables in this terminal, run: . /tmp/infisical_vars"
    
    # Optional: Automatically load for every new bash terminal
    echo ". /tmp/infisical_vars" >> ~/.bashrc
    
    tail -f /dev/null
else
    echo "🚀 Starting Chainlit server..."
    exec chainlit run chainlit_app.py --host 0.0.0.0 --port 8010
fi