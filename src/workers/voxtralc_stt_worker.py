"""
voxtral.c STT Worker - Speech-to-text using antirez/voxtral.c native binary.

This worker wraps the voxtral.c CLI tool, which is a pure C implementation of
Mistral's Voxtral Realtime 4B model. On Apple Silicon it uses Metal GPU
acceleration with zero external dependencies.

Requires: compiled voxtral binary + downloaded model directory.
Run scripts/setup-voxtralc.sh to set up both.
"""

import base64
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile, File, Form
from pydantic import BaseModel

from .base import BaseWorker


class TranscriptionResponse(BaseModel):
    text: str
    language: Optional[str] = None
    duration: Optional[float] = None


class VoxtralCSTTWorker(BaseWorker):
    """Speech-to-Text worker using voxtral.c native binary."""

    def __init__(self, alias: str, model_path: str, port: int, **params):
        super().__init__(alias, model_path, port)
        self.params = params
        self._binary_path: Optional[str] = None
        self._model_dir: Optional[str] = None
        self._interval: float = 2.0
        self._setup_stt_routes()

    def _setup_stt_routes(self):
        """Setup STT-specific routes."""

        @self.app.post("/transcribe", response_model=TranscriptionResponse)
        async def transcribe(
            file: Optional[UploadFile] = File(None),
            audio_base64: Optional[str] = Form(None),
            language: Optional[str] = Form(None),
            task: str = Form("transcribe"),
        ):
            """Transcribe audio to text using voxtral.c."""
            if file is None and audio_base64 is None:
                raise HTTPException(
                    status_code=400,
                    detail="Either file or audio_base64 must be provided",
                )

            try:
                if file:
                    audio_data = await file.read()
                else:
                    audio_data = base64.b64decode(audio_base64)

                # Write to temp WAV file
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(audio_data)
                    temp_path = f.name

                try:
                    result = self._transcribe(temp_path)
                    return result
                finally:
                    Path(temp_path).unlink(missing_ok=True)

            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/v1/audio/transcriptions")
        async def openai_transcribe(
            file: UploadFile = File(...),
            model: str = Form("whisper-1"),
            language: Optional[str] = Form(None),
            response_format: str = Form("json"),
        ):
            """OpenAI-compatible transcription endpoint."""
            audio_data = await file.read()

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_data)
                temp_path = f.name

            try:
                result = self._transcribe(temp_path)

                if response_format == "text":
                    return result.text
                return {"text": result.text}
            finally:
                Path(temp_path).unlink(missing_ok=True)

    def load_model(self):
        """Validate voxtral.c binary and model directory exist."""
        # Resolve binary path from params or default
        self._binary_path = self.params.get("binary_path", "./bin/voxtral")
        self._model_dir = self.model_path
        self._interval = float(self.params.get("interval", 2.0))

        # Resolve relative paths from project root
        if not os.path.isabs(self._binary_path):
            self._binary_path = os.path.abspath(self._binary_path)
        if not os.path.isabs(self._model_dir):
            self._model_dir = os.path.abspath(self._model_dir)

        # Validate binary
        if not os.path.isfile(self._binary_path):
            raise RuntimeError(
                f"voxtral binary not found at {self._binary_path}. "
                "Run: bash scripts/setup-voxtralc.sh"
            )
        if not os.access(self._binary_path, os.X_OK):
            raise RuntimeError(
                f"voxtral binary at {self._binary_path} is not executable."
            )

        # Validate model directory
        model_dir = Path(self._model_dir)
        if not model_dir.is_dir():
            raise RuntimeError(
                f"Model directory not found at {self._model_dir}. "
                "Run: bash scripts/setup-voxtralc.sh"
            )

        required_files = ["consolidated.safetensors", "tekken.json"]
        for fname in required_files:
            if not (model_dir / fname).exists():
                raise RuntimeError(
                    f"Missing {fname} in model directory {self._model_dir}. "
                    "Run: bash scripts/setup-voxtralc.sh"
                )

        # Quick version check
        try:
            result = subprocess.run(
                [self._binary_path, "-h"],
                capture_output=True, text=True, timeout=5,
            )
            print(f"[*] voxtral.c binary validated: {self._binary_path}")
        except Exception as e:
            print(f"[!] Warning: could not verify voxtral binary: {e}")

        print(f"[*] voxtral.c STT Worker ready")
        print(f"[*] Binary: {self._binary_path}")
        print(f"[*] Model dir: {self._model_dir}")
        print(f"[*] Encoder interval: {self._interval}s")

    def _transcribe(self, audio_path: str) -> TranscriptionResponse:
        """Transcribe audio file using voxtral.c CLI."""
        cmd = [
            self._binary_path,
            "-d", self._model_dir,
            "-i", audio_path,
            "-I", str(self._interval),
            "--silent",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            if result.returncode != 0:
                stderr = result.stderr.strip()
                raise RuntimeError(
                    f"voxtral.c exited with code {result.returncode}: {stderr}"
                )

            text = result.stdout.strip()

            return TranscriptionResponse(text=text)

        except subprocess.TimeoutExpired:
            raise RuntimeError("voxtral.c transcription timed out (300s)")


def main():
    args = VoxtralCSTTWorker.parse_args()

    # Load params from config via environment variable (set by worker manager)
    import json
    params = json.loads(os.environ.get("WORKER_PARAMS", "{}"))

    worker = VoxtralCSTTWorker(
        alias=args.alias,
        model_path=args.model_path,
        port=args.port,
        **params,
    )
    worker.run()


if __name__ == "__main__":
    main()
