.PHONY: install install-worker start stop restart logs status test clean

# Installation
install:
	uv sync
	@echo "Gateway dependencies installed"

install-worker:
	uv sync --extra worker
	@echo "Worker dependencies installed (MLX)"

# Development
dev-gateway:
	PYTHONPATH=. uv run python -m src.gateway.main

dev-manager:
	PYTHONPATH=. uv run python -m src.worker_manager

# Docker operations
build:
	docker compose build

start:
	docker compose up -d

stop:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f gateway

logs-manager:
	@if [ -f /tmp/voice-insight-worker-manager.log ]; then \
		tail -f /tmp/voice-insight-worker-manager.log; \
	else \
		echo "Worker manager log not found. Is the service running?"; \
	fi

# Service management (macOS)
service-install:
	./scripts/install-service.sh

service-start:
	launchctl load ~/Library/LaunchAgents/com.voice-insight.worker-manager.plist

service-stop:
	launchctl unload ~/Library/LaunchAgents/com.voice-insight.worker-manager.plist

service-restart: service-stop service-start

service-uninstall:
	./scripts/uninstall-service.sh

# Full stack
start-all: service-start start
	@echo "Voice Insight API started"

stop-all: stop service-stop
	@echo "Voice Insight API stopped"

# Status
status:
	@echo "=== Gateway (Docker) ==="
	@docker compose ps 2>/dev/null || echo "Not running"
	@echo ""
	@echo "=== Worker Manager (Host) ==="
	@curl -s http://localhost:8210/status 2>/dev/null | python3 -m json.tool || echo "Not running"

# Testing
test:
	uv run pytest tests/ -v

test-stt:
	@echo "Testing STT..."
	curl -X POST "http://localhost:8200/v1/audio/transcriptions" \
		-F "file=@test.wav" \
		-F "model=stt-fast"

test-tts:
	@echo "Testing TTS..."
	curl -X POST "http://localhost:8200/v1/audio/speech" \
		-H "Content-Type: application/json" \
		-d '{"input": "Hello, this is a test.", "model": "tts-fast"}' \
		--output test-output.wav

# Cleanup
clean:
	docker compose down -v --remove-orphans
	rm -rf .venv __pycache__ .pytest_cache
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Pre-download models
download-models:
	@echo "Downloading STT models..."
	uv run python -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/whisper-large-v3-turbo')"
	@echo "Downloading TTS models..."
	uv run python -c "from huggingface_hub import snapshot_download; snapshot_download('mlx-community/Kokoro-82M-bf16')"
	@echo "Models downloaded"
