"""Load and validate configuration from config.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel


class STTConfig(BaseModel):
    endpoint: str = "http://localhost:8200"
    model: str = "stt-fast"
    language: Optional[str] = None


class LLMConfig(BaseModel):
    endpoint: str = "http://localhost:8400"
    model: str = "llm-small"
    system_prompt: str = (
        "You are a helpful voice assistant. "
        "Keep responses concise and conversational (2-3 sentences max)."
    )
    max_tokens: int = 256
    temperature: float = 0.7


class TTSConfig(BaseModel):
    endpoint: str = "http://localhost:8200"
    model: str = "tts-fast"
    voice: str = "af_heart"
    speed: float = 1.0


class ServicesConfig(BaseModel):
    stt: STTConfig = STTConfig()
    llm: LLMConfig = LLMConfig()
    tts: TTSConfig = TTSConfig()


class PipelineConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8800
    max_audio_duration_seconds: int = 60
    conversation_history_limit: int = 10


class AppConfig(BaseModel):
    services: ServicesConfig = ServicesConfig()
    pipeline: PipelineConfig = PipelineConfig()


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load configuration from a YAML file.

    Resolution order:
      1. Explicit *path* argument
      2. ``VOICE_ASSISTANT_CONFIG`` environment variable
      3. ``config.yaml`` in the project root (next to pyproject.toml)
    """
    if path is None:
        path = os.environ.get("VOICE_ASSISTANT_CONFIG")
    if path is None:
        path = Path(__file__).resolve().parents[2] / "config.yaml"

    path = Path(path)
    if not path.exists():
        return AppConfig()

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    return AppConfig.model_validate(raw)
