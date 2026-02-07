#!/bin/bash
# TTS Benchmark Script for Voice-Insight-API
# Tests text-to-speech synthesis quality and latency

set -e

BASE_URL="${BASE_URL:-http://localhost:8200}"
OUTPUT_DIR="./benchmarks/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Benchmark prompt - consistent text for quality comparison across model changes
BENCHMARK_TEXT="The quick brown fox jumps over the lazy dog. This sentence contains every letter of the English alphabet, making it perfect for evaluating text-to-speech quality and pronunciation accuracy."

# Configuration
VOICE="${VOICE:-af_heart}"
MODEL="${MODEL:-tts-fast}"
FORMAT="${FORMAT:-wav}"

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

echo "=== TTS Benchmark ==="
echo "Timestamp: $TIMESTAMP"
echo "Model: $MODEL"
echo "Voice: $VOICE"
echo "Text: $BENCHMARK_TEXT"
echo ""

# Measure latency
START_TIME=$(python3 -c "import time; print(time.time())")

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/v1/audio/speech" \
  -H "Content-Type: application/json" \
  -d "{
    \"input\": \"$BENCHMARK_TEXT\",
    \"model\": \"$MODEL\",
    \"voice\": \"$VOICE\",
    \"response_format\": \"$FORMAT\"
  }" \
  --output "$OUTPUT_DIR/tts_${TIMESTAMP}.${FORMAT}")

END_TIME=$(python3 -c "import time; print(time.time())")
HTTP_CODE=$(echo "$RESPONSE" | tail -1)

# Calculate latency
LATENCY=$(python3 -c "print(f'{$END_TIME - $START_TIME:.2f}')")

# Get file info
OUTPUT_FILE="$OUTPUT_DIR/tts_${TIMESTAMP}.${FORMAT}"
if [ -f "$OUTPUT_FILE" ]; then
    FILE_SIZE=$(stat -f%z "$OUTPUT_FILE" 2>/dev/null || stat -c%s "$OUTPUT_FILE" 2>/dev/null)

    # Get audio duration using ffprobe if available
    if command -v ffprobe &> /dev/null; then
        DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUTPUT_FILE" 2>/dev/null || echo "N/A")
    else
        DURATION="N/A (install ffmpeg for duration)"
    fi
else
    FILE_SIZE=0
    DURATION="N/A"
fi

echo "=== Results ==="
echo "HTTP Status: $HTTP_CODE"
echo "Latency: ${LATENCY}s"
echo "File Size: $FILE_SIZE bytes"
echo "Duration: ${DURATION}s"
echo "Output: $OUTPUT_FILE"

# Save metadata
cat > "$OUTPUT_DIR/tts_${TIMESTAMP}.json" << EOF
{
  "timestamp": "$TIMESTAMP",
  "type": "tts",
  "model": "$MODEL",
  "voice": "$VOICE",
  "format": "$FORMAT",
  "text": "$BENCHMARK_TEXT",
  "http_status": $HTTP_CODE,
  "latency_seconds": $LATENCY,
  "file_size_bytes": $FILE_SIZE,
  "duration_seconds": "$DURATION",
  "output_file": "$OUTPUT_FILE"
}
EOF

echo "Metadata: $OUTPUT_DIR/tts_${TIMESTAMP}.json"

# Preview on macOS
if [[ "$OSTYPE" == "darwin"* ]] && [ -f "$OUTPUT_FILE" ] && [ "$HTTP_CODE" == "200" ]; then
    echo ""
    read -p "Play audio? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        afplay "$OUTPUT_FILE"
    fi
fi
