"""Tests for configuration loading."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.core.config import AppConfig, load_config


def test_default_config():
    """AppConfig with no arguments should produce valid defaults."""
    cfg = AppConfig()
    assert cfg.services.stt.endpoint == "http://localhost:8200"
    assert cfg.services.llm.model == "llm-small"
    assert cfg.services.tts.voice == "af_heart"
    assert cfg.pipeline.port == 8800


def test_load_config_from_file(tmp_path: Path):
    """load_config should parse a YAML file correctly."""
    yaml_content = textwrap.dedent("""\
        services:
          stt:
            endpoint: "http://stt-host:9000"
            model: "stt-large"
            language: "ko"
          llm:
            endpoint: "http://llm-host:9001"
            model: "llm-large"
            max_tokens: 512
            temperature: 0.3
          tts:
            endpoint: "http://tts-host:9002"
            model: "tts-large"
            voice: "bf_emma"
            speed: 1.2
        pipeline:
          port: 9999
          max_audio_duration_seconds: 30
          conversation_history_limit: 5
    """)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml_content)

    cfg = load_config(cfg_path)
    assert cfg.services.stt.endpoint == "http://stt-host:9000"
    assert cfg.services.stt.language == "ko"
    assert cfg.services.llm.model == "llm-large"
    assert cfg.services.llm.max_tokens == 512
    assert cfg.services.tts.voice == "bf_emma"
    assert cfg.services.tts.speed == 1.2
    assert cfg.pipeline.port == 9999
    assert cfg.pipeline.conversation_history_limit == 5


def test_load_config_missing_file(tmp_path: Path):
    """load_config should return defaults when the file does not exist."""
    cfg = load_config(tmp_path / "nonexistent.yaml")
    assert cfg.pipeline.port == 8800


def test_load_config_empty_file(tmp_path: Path):
    """load_config should handle an empty YAML file gracefully."""
    cfg_path = tmp_path / "empty.yaml"
    cfg_path.write_text("")
    cfg = load_config(cfg_path)
    assert cfg.pipeline.port == 8800


def test_load_config_partial(tmp_path: Path):
    """Partially specified config should merge with defaults."""
    yaml_content = textwrap.dedent("""\
        services:
          llm:
            model: "llm-medium"
    """)
    cfg_path = tmp_path / "partial.yaml"
    cfg_path.write_text(yaml_content)

    cfg = load_config(cfg_path)
    assert cfg.services.llm.model == "llm-medium"
    # Other values stay at defaults
    assert cfg.services.stt.model == "stt-fast"
    assert cfg.pipeline.port == 8800
