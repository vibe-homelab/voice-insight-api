"""Tests for configuration."""

import pytest

from src.core.config import load_config, AppConfig


def test_load_config():
    """Test loading configuration."""
    config = load_config("config.yaml")
    assert isinstance(config, AppConfig)


def test_config_models():
    """Test model configuration."""
    config = load_config("config.yaml")
    assert "stt-fast" in config.models
    assert "tts-fast" in config.models


def test_config_memory():
    """Test memory configuration."""
    config = load_config("config.yaml")
    assert config.memory.max_unified_memory_gb == 24
    assert config.memory.safety_margin_gb == 2.0


def test_config_workers():
    """Test worker configuration."""
    config = load_config("config.yaml")
    assert config.workers.manager_port == 8100
    assert config.workers.idle_timeout_seconds == 300
