#!/bin/sh
set -e

MODEL_DIR="/app/hf_cache/florence-2-large"
# Define a "sentinel" file that we know we keep after cleanup
# If this file exists, we assume the download and cleanup are done.
SENTINEL_FILE="$MODEL_DIR/model.safetensors"

if [ -f "$SENTINEL_FILE" ]; then
    echo "✅ Model weights and cleanup already verified. Skipping."
else
    echo "⬇️ Downloading model weights..."
    huggingface-cli download microsoft/Florence-2-large --local-dir "$MODEL_DIR"
    
    echo "🧹 Cleaning up redundant files..."
    
    # Remove files that are NOT needed for inference
    rm -f "$MODEL_DIR/pytorch_model.bin"
    rm -rf "$MODEL_DIR/.cache"
    rm -rf "$MODEL_DIR/.git"
    rm -f "$MODEL_DIR/sample_inference.ipynb" \
          "$MODEL_DIR/README.md" \
          "$MODEL_DIR/CODE_OF_CONDUCT.md" \
          "$MODEL_DIR/SECURITY.md" \
          "$MODEL_DIR/SUPPORT.md" \
          "$MODEL_DIR/LICENSE" \
          "$MODEL_DIR/.gitattributes"
          
    echo "✅ Download and cleanup complete."
fi