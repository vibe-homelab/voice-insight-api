#!/bin/bash
# STT Benchmark Script for Voice-Insight-API
# Tests speech-to-text transcription quality and latency

set -e

BASE_URL="${BASE_URL:-http://localhost:8200}"
OUTPUT_DIR="./benchmarks/results"
SAMPLE_DIR="./benchmarks/samples"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Configuration
MODEL="${MODEL:-stt-fast}"
LANGUAGE="${LANGUAGE:-en}"

# Sample audio file - use provided or default benchmark sample
AUDIO_FILE="${1:-$SAMPLE_DIR/benchmark_sample.wav}"

# Expected transcription for accuracy comparison
EXPECTED_TEXT="The quick brown fox jumps over the lazy dog. This sentence contains every letter of the English alphabet, making it perfect for evaluating text-to-speech quality and pronunciation accuracy."

# Ensure output directory exists
mkdir -p "$OUTPUT_DIR"

echo "=== STT Benchmark ==="
echo "Timestamp: $TIMESTAMP"
echo "Model: $MODEL"
echo "Language: $LANGUAGE"
echo "Audio File: $AUDIO_FILE"
echo ""

# Check if audio file exists
if [ ! -f "$AUDIO_FILE" ]; then
    echo "Error: Audio file not found: $AUDIO_FILE"
    echo ""
    echo "To create a benchmark sample, run TTS first:"
    echo "  ./scripts/test-tts.sh"
    echo "  cp ./benchmarks/results/tts_*.wav $SAMPLE_DIR/benchmark_sample.wav"
    echo ""
    echo "Or provide a custom audio file:"
    echo "  ./scripts/test-stt.sh /path/to/audio.wav"
    exit 1
fi

# Get audio file info
FILE_SIZE=$(stat -f%z "$AUDIO_FILE" 2>/dev/null || stat -c%s "$AUDIO_FILE" 2>/dev/null)
if command -v ffprobe &> /dev/null; then
    AUDIO_DURATION=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$AUDIO_FILE" 2>/dev/null || echo "N/A")
else
    AUDIO_DURATION="N/A"
fi

echo "Audio Size: $FILE_SIZE bytes"
echo "Audio Duration: ${AUDIO_DURATION}s"
echo ""

# Measure latency
START_TIME=$(python3 -c "import time; print(time.time())")

RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$BASE_URL/v1/audio/transcriptions" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@$AUDIO_FILE" \
  -F "model=$MODEL" \
  -F "language=$LANGUAGE")

END_TIME=$(python3 -c "import time; print(time.time())")

# Parse response
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

# Calculate latency
LATENCY=$(python3 -c "print(f'{$END_TIME - $START_TIME:.2f}')")

# Extract transcription text
TRANSCRIBED_TEXT=$(echo "$BODY" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('text', 'ERROR'))" 2>/dev/null || echo "Parse Error")

# Calculate Real-Time Factor (RTF) if duration available
if [ "$AUDIO_DURATION" != "N/A" ]; then
    RTF=$(python3 -c "print(f'{$LATENCY / $AUDIO_DURATION:.3f}')")
else
    RTF="N/A"
fi

echo "=== Results ==="
echo "HTTP Status: $HTTP_CODE"
echo "Latency: ${LATENCY}s"
echo "Real-Time Factor: $RTF (lower is better, <1.0 = faster than real-time)"
echo ""
echo "Transcription:"
echo "  $TRANSCRIBED_TEXT"
echo ""

# Save metadata
cat > "$OUTPUT_DIR/stt_${TIMESTAMP}.json" << EOF
{
  "timestamp": "$TIMESTAMP",
  "type": "stt",
  "model": "$MODEL",
  "language": "$LANGUAGE",
  "audio_file": "$AUDIO_FILE",
  "audio_size_bytes": $FILE_SIZE,
  "audio_duration_seconds": "$AUDIO_DURATION",
  "http_status": $HTTP_CODE,
  "latency_seconds": $LATENCY,
  "real_time_factor": "$RTF",
  "transcribed_text": $(echo "$TRANSCRIBED_TEXT" | python3 -c "import sys, json; print(json.dumps(sys.stdin.read().strip()))"),
  "expected_text": $(echo "$EXPECTED_TEXT" | python3 -c "import sys, json; print(json.dumps(sys.stdin.read().strip()))")
}
EOF

echo "Metadata: $OUTPUT_DIR/stt_${TIMESTAMP}.json"

# Word Error Rate calculation (basic)
if [ "$HTTP_CODE" == "200" ] && [ "$TRANSCRIBED_TEXT" != "Parse Error" ]; then
    echo ""
    echo "=== Quality Check ==="
    # Simple word count comparison
    EXPECTED_WORDS=$(echo "$EXPECTED_TEXT" | wc -w | tr -d ' ')
    TRANSCRIBED_WORDS=$(echo "$TRANSCRIBED_TEXT" | wc -w | tr -d ' ')
    echo "Expected words: $EXPECTED_WORDS"
    echo "Transcribed words: $TRANSCRIBED_WORDS"
fi
