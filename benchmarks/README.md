# Voice-Insight-API Benchmarks

Performance benchmarks for TTS (Text-to-Speech) and STT (Speech-to-Text) models.

## Directory Structure

```
benchmarks/
├── samples/           # Reference audio files for STT testing
│   └── benchmark_sample.wav   # Standard test audio
├── results/           # Benchmark outputs with timestamps
│   ├── tts_YYYYMMDD_HHMMSS.wav
│   ├── tts_YYYYMMDD_HHMMSS.json
│   ├── stt_YYYYMMDD_HHMMSS.json
│   └── ...
└── README.md
```

## Quick Start

### 1. TTS Benchmark

```bash
# Default: tts-fast model, af_heart voice
./scripts/test-tts.sh

# Custom model/voice
MODEL=tts-stream VOICE=af_sky ./scripts/test-tts.sh
```

### 2. STT Benchmark

```bash
# First, create a benchmark sample from TTS output
./scripts/test-tts.sh
cp ./benchmarks/results/tts_*.wav ./benchmarks/samples/benchmark_sample.wav

# Run STT benchmark
./scripts/test-stt.sh

# Or use custom audio file
./scripts/test-stt.sh /path/to/your/audio.wav

# Custom model
MODEL=stt-best ./scripts/test-stt.sh
```

## Benchmark Prompt

The standard benchmark text (pangram + extended):

> "The quick brown fox jumps over the lazy dog. This sentence contains every letter of the English alphabet, making it perfect for evaluating text-to-speech quality and pronunciation accuracy."

This text is used for:
- **TTS**: Consistent synthesis quality comparison
- **STT**: Accuracy measurement against known reference

## Metrics

### TTS Metrics
- **Latency**: Time to generate audio
- **File Size**: Output audio size in bytes
- **Duration**: Length of generated audio

### STT Metrics
- **Latency**: Time to transcribe
- **Real-Time Factor (RTF)**: Latency / Audio Duration
  - RTF < 1.0 = faster than real-time
  - RTF = 0.5 = 2x real-time speed
- **Word Count**: Basic accuracy indicator

## Comparing Results

Results are stored with timestamps, making it easy to compare across model changes:

```bash
# List all TTS results
ls -la benchmarks/results/tts_*.json

# Compare latencies
jq -r '[.timestamp, .model, .latency_seconds] | @tsv' benchmarks/results/tts_*.json

# Compare STT RTF
jq -r '[.timestamp, .model, .real_time_factor] | @tsv' benchmarks/results/stt_*.json
```

## Environment Variables

| Variable   | Default           | Description              |
|------------|-------------------|--------------------------|
| BASE_URL   | http://localhost:8200 | API endpoint         |
| MODEL      | tts-fast / stt-fast | Model to use          |
| VOICE      | af_heart          | TTS voice              |
| FORMAT     | wav               | TTS output format      |
| LANGUAGE   | en                | STT language           |
