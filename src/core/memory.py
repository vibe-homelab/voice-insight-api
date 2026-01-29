"""Memory monitoring for Apple Silicon unified memory."""

import subprocess
from dataclasses import dataclass
from typing import Dict

# Model memory requirements (empirically measured)
MODEL_MEMORY_REQUIREMENTS: Dict[str, float] = {
    # STT Models
    "mlx-community/whisper-large-v3-turbo": 1.5,
    "mlx-community/whisper-large-v3-mlx": 3.0,
    "mlx-community/whisper-large-v3-turbo-asr-fp16": 1.5,
    "mlx-community/distil-whisper-large-v3": 1.2,
    # TTS Models
    "mlx-community/Kokoro-82M-bf16": 0.5,
    "Marvis-AI/marvis-tts-250m-v0.1": 1.0,
}


@dataclass
class MemoryStatus:
    total_gb: float
    used_gb: float
    available_gb: float
    app_memory_gb: float
    wired_gb: float
    compressed_gb: float

    @property
    def usage_percent(self) -> float:
        return (self.used_gb / self.total_gb) * 100 if self.total_gb > 0 else 0


def get_memory_status() -> MemoryStatus:
    """Get current memory status using vm_stat (macOS)."""
    try:
        # Get total memory from sysctl
        total_result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            check=True,
        )
        total_bytes = int(total_result.stdout.strip())
        total_gb = total_bytes / (1024**3)

        # Parse vm_stat output
        vm_result = subprocess.run(
            ["vm_stat"],
            capture_output=True,
            text=True,
            check=True,
        )

        stats = {}
        for line in vm_result.stdout.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                value = value.strip().rstrip(".")
                try:
                    stats[key.strip()] = int(value)
                except ValueError:
                    pass

        # Page size is typically 16KB on Apple Silicon
        page_size = 16384

        def pages_to_gb(pages: int) -> float:
            return (pages * page_size) / (1024**3)

        # Calculate memory breakdown
        free_pages = stats.get("Pages free", 0)
        active_pages = stats.get("Pages active", 0)
        inactive_pages = stats.get("Pages inactive", 0)
        speculative_pages = stats.get("Pages speculative", 0)
        wired_pages = stats.get("Pages wired down", 0)
        compressed_pages = stats.get("Pages occupied by compressor", 0)
        purgeable_pages = stats.get("Pages purgeable", 0)

        # Available = free + inactive + purgeable + speculative
        available_pages = free_pages + inactive_pages + purgeable_pages + speculative_pages

        # App memory = active + wired
        app_memory_pages = active_pages + wired_pages

        available_gb = pages_to_gb(available_pages)
        app_memory_gb = pages_to_gb(app_memory_pages)
        wired_gb = pages_to_gb(wired_pages)
        compressed_gb = pages_to_gb(compressed_pages)
        used_gb = total_gb - available_gb

        return MemoryStatus(
            total_gb=total_gb,
            used_gb=used_gb,
            available_gb=available_gb,
            app_memory_gb=app_memory_gb,
            wired_gb=wired_gb,
            compressed_gb=compressed_gb,
        )

    except (subprocess.CalledProcessError, ValueError, KeyError) as e:
        # Fallback with safe defaults
        return MemoryStatus(
            total_gb=32.0,
            used_gb=16.0,
            available_gb=16.0,
            app_memory_gb=8.0,
            wired_gb=4.0,
            compressed_gb=2.0,
        )


def get_model_memory_requirement(model_path: str, model_type: str) -> float:
    """Get estimated memory requirement for a model."""
    # Check known models first
    if model_path in MODEL_MEMORY_REQUIREMENTS:
        return MODEL_MEMORY_REQUIREMENTS[model_path]

    # Estimate based on model type
    if model_type == "stt":
        if "turbo" in model_path.lower():
            return 1.5
        if "large" in model_path.lower():
            return 3.0
        if "medium" in model_path.lower():
            return 1.5
        if "small" in model_path.lower():
            return 0.5
        return 2.0  # Default for STT

    if model_type == "tts":
        if "250m" in model_path.lower():
            return 1.0
        if "82m" in model_path.lower():
            return 0.5
        return 1.0  # Default for TTS

    return 2.0  # Generic default


def can_load_model(model_path: str, model_type: str, safety_margin_gb: float = 2.0) -> bool:
    """Check if there's enough memory to load a model."""
    required_gb = get_model_memory_requirement(model_path, model_type)
    status = get_memory_status()
    return status.available_gb >= (required_gb + safety_margin_gb)
