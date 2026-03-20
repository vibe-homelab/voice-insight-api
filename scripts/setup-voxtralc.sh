#!/usr/bin/env bash
# Setup voxtral.c — clone, build, and download model for voice-insight-api.
# Requires: git, make, C compiler (Xcode CLI tools on macOS).
#
# Usage:
#   bash scripts/setup-voxtralc.sh
#
# After running, you'll have:
#   ./bin/voxtral           — compiled binary
#   ./models/voxtral/       — model weights + tokenizer (~8.9 GB)

set -euo pipefail

REPO_URL="https://github.com/antirez/voxtral.c.git"
BUILD_DIR=".build/voxtral.c"
BIN_DIR="bin"
MODEL_DIR="models/voxtral"

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"

echo "=== voxtral.c setup ==="
echo "Project root: $PROJECT_ROOT"

# ── 1. Clone or update source ────────────────────────────────
if [ -d "$BUILD_DIR" ]; then
    echo "Updating existing voxtral.c source..."
    git -C "$BUILD_DIR" pull --ff-only || true
else
    echo "Cloning voxtral.c..."
    mkdir -p "$(dirname "$BUILD_DIR")"
    git clone "$REPO_URL" "$BUILD_DIR"
fi

# ── 2. Build ─────────────────────────────────────────────────
echo "Building voxtral.c..."
cd "$BUILD_DIR"

ARCH="$(uname -m)"
OS="$(uname -s)"

if [ "$OS" = "Darwin" ]; then
    if [ "$ARCH" = "arm64" ]; then
        echo "Detected Apple Silicon — building with Metal (MPS)..."
        make clean 2>/dev/null || true
        make mps
    else
        echo "Detected Intel Mac — building with BLAS (Accelerate)..."
        make clean 2>/dev/null || true
        make blas
    fi
elif [ "$OS" = "Linux" ]; then
    echo "Detected Linux — building with BLAS (OpenBLAS)..."
    echo "Note: install libopenblas-dev if build fails."
    make clean 2>/dev/null || true
    make blas
else
    echo "Unsupported OS: $OS"
    exit 1
fi

# ── 3. Install binary ────────────────────────────────────────
cd "$PROJECT_ROOT"
mkdir -p "$BIN_DIR"
cp "$BUILD_DIR/voxtral" "$BIN_DIR/voxtral"
chmod +x "$BIN_DIR/voxtral"
echo "Binary installed: $BIN_DIR/voxtral"

# ── 4. Download model ────────────────────────────────────────
if [ -f "$MODEL_DIR/consolidated.safetensors" ]; then
    echo "Model already downloaded at $MODEL_DIR — skipping."
else
    echo "Downloading Voxtral model (~8.9 GB)..."
    mkdir -p "$MODEL_DIR"

    # Use voxtral.c's download script if available
    if [ -f "$BUILD_DIR/download_model.sh" ]; then
        cd "$BUILD_DIR"
        bash download_model.sh
        # Move model files to our model directory
        if [ -d "$BUILD_DIR/model" ]; then
            cp "$BUILD_DIR/model/"* "$PROJECT_ROOT/$MODEL_DIR/"
        elif [ -d "$BUILD_DIR/voxtral-model" ]; then
            cp "$BUILD_DIR/voxtral-model/"* "$PROJECT_ROOT/$MODEL_DIR/"
        else
            # Find the safetensors file wherever it ended up
            MODEL_FILE=$(find "$BUILD_DIR" -name "consolidated.safetensors" -type f 2>/dev/null | head -1)
            if [ -n "$MODEL_FILE" ]; then
                MODEL_SRC_DIR="$(dirname "$MODEL_FILE")"
                cp "$MODEL_SRC_DIR/"* "$PROJECT_ROOT/$MODEL_DIR/"
            else
                echo "ERROR: download_model.sh ran but model files not found."
                echo "Please download manually and place in $MODEL_DIR/"
                exit 1
            fi
        fi
        cd "$PROJECT_ROOT"
    else
        echo "download_model.sh not found in voxtral.c repo."
        echo "Please download the model manually:"
        echo "  1. Visit https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602"
        echo "  2. Download consolidated.safetensors and tekken.json"
        echo "  3. Place them in $MODEL_DIR/"
        exit 1
    fi
fi

# ── 5. Validate ──────────────────────────────────────────────
echo ""
echo "=== Validation ==="

if [ -x "$BIN_DIR/voxtral" ]; then
    echo "[OK] Binary: $BIN_DIR/voxtral"
else
    echo "[FAIL] Binary not found or not executable"
    exit 1
fi

if [ -f "$MODEL_DIR/consolidated.safetensors" ]; then
    echo "[OK] Model weights: $MODEL_DIR/consolidated.safetensors"
else
    echo "[FAIL] Model weights not found"
    exit 1
fi

if [ -f "$MODEL_DIR/tekken.json" ]; then
    echo "[OK] Tokenizer: $MODEL_DIR/tekken.json"
else
    echo "[WARN] tekken.json not found — transcription may fail"
fi

echo ""
echo "=== Setup complete ==="
echo "voxtral.c is ready. Use model alias 'stt-voxtralc' in API requests."
echo ""
echo "Quick test:"
echo "  ./bin/voxtral -d ./models/voxtral -i test.wav --silent"
