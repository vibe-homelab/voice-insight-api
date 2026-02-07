"""Configuration loading and validation."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel


class ModelParams(BaseModel):
    memory_gb: float = 1.0
    batch_size: int = 12
    language: Optional[str] = None
    voice: Optional[str] = None
    speed: float = 1.0
    streaming: bool = False


class ModelConfig(BaseModel):
    type: str  # "stt" or "tts"
    path: str  # HuggingFace model path
    hot_reload: bool = False
    params: Dict[str, Any] = {}

    @property
    def parsed_params(self) -> ModelParams:
        return ModelParams(**self.params)


class MemoryConfig(BaseModel):
    max_unified_memory_gb: float = 24.0
    eviction_threshold_percent: int = 75
    safety_margin_gb: float = 2.0


class GatewayConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8200
    api_key: str = ""


class WorkersConfig(BaseModel):
    manager_port: int = 8210
    base_port: int = 8211
    idle_timeout_seconds: int = 300
    health_check_interval: int = 30
    startup_timeout: int = 120


class AppConfig(BaseModel):
    models: Dict[str, ModelConfig]
    memory: MemoryConfig = MemoryConfig()
    gateway: GatewayConfig = GatewayConfig()
    workers: WorkersConfig = WorkersConfig()


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """Load configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    cfg = AppConfig(**data)

    # Optional environment overrides (useful for container/runtime configs).
    # Kept intentionally minimal and compatible with README variables.
    if os.getenv("GATEWAY_PORT"):
        cfg.gateway.port = int(os.environ["GATEWAY_PORT"])
    if os.getenv("GATEWAY_API_KEY"):
        cfg.gateway.api_key = os.environ["GATEWAY_API_KEY"]
    if os.getenv("MANAGER_PORT"):
        cfg.workers.manager_port = int(os.environ["MANAGER_PORT"])
    if os.getenv("BASE_PORT"):
        cfg.workers.base_port = int(os.environ["BASE_PORT"])
    if os.getenv("IDLE_TIMEOUT"):
        cfg.workers.idle_timeout_seconds = int(os.environ["IDLE_TIMEOUT"])

    return cfg


# Global config instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
