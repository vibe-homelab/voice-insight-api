"""
CUDA TTS Worker - Qwen3-TTS text-to-speech via PyTorch/CUDA.

Supports:
- POST /synthesize  (base64 JSON response)
- POST /clone       (voice cloning with reference audio)
- POST /v1/audio/speech  (OpenAI-compatible, returns audio stream)
- GET  /health

Requires: qwen-tts, soundfile, torch
"""

import base64
import io
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import Body, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .base import BaseWorker

MODEL_ID = os.getenv("MODEL_ID", "Qwen/Qwen3-TTS-12Hz-1.7B-Base")


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    speed: float = 1.0
    format: str = "wav"
    stream: bool = False


class TTSResponse(BaseModel):
    audio_base64: str
    format: str
    duration: Optional[float] = None


class CloneRequest(BaseModel):
    text: str
    reference_audio: str  # base64-encoded reference audio
    reference_text: Optional[str] = None  # transcript of reference audio


class OpenAISpeechRequest(BaseModel):
    model: str = "tts-1"
    input: str
    voice: str = "default"
    response_format: str = "wav"
    speed: float = 1.0


class CUDATTSWorker(BaseWorker):
    """Text-to-Speech worker using Qwen3-TTS on NVIDIA GPU."""

    def __init__(self, alias: str, model_path: str, port: int, **params):
        super().__init__(alias, model_path, port)
        self.params = params
        self._model_id = model_path or MODEL_ID
        self.tts_model = None
        self._setup_tts_routes()

    def _setup_tts_routes(self):
        """Setup TTS-specific routes."""

        @self.app.post("/synthesize")
        async def synthesize(request: TTSRequest):
            """Synthesize speech from text."""
            if self.tts_model is None:
                raise HTTPException(status_code=503, detail="Model not loaded")

            try:
                audio_data, duration = self._generate(
                    request.text,
                    speaker=request.voice or "Sohee",
                    speed=request.speed,
                )

                return TTSResponse(
                    audio_base64=base64.b64encode(audio_data).decode(),
                    format=request.format,
                    duration=duration,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/clone")
        async def clone(request: CloneRequest):
            """Voice cloning with reference audio."""
            if self.tts_model is None:
                raise HTTPException(status_code=503, detail="Model not loaded")

            try:
                # Decode reference audio
                ref_audio_bytes = base64.b64decode(request.reference_audio)

                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(ref_audio_bytes)
                    ref_path = f.name

                try:
                    audio_data, duration = self._generate_clone(
                        request.text,
                        ref_audio_path=ref_path,
                        ref_text=request.reference_text,
                    )
                finally:
                    Path(ref_path).unlink(missing_ok=True)

                return TTSResponse(
                    audio_base64=base64.b64encode(audio_data).decode(),
                    format="wav",
                    duration=duration,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/v1/audio/speech")
        async def openai_speech(
            body: OpenAISpeechRequest | None = Body(default=None),
            model: str = Query(default="tts-1"),
            input_text: str = Query(default="", alias="input"),
            voice: str = Query(default="default"),
            response_format: str = Query(default="wav"),
            speed: float = Query(default=1.0),
        ):
            """OpenAI-compatible speech endpoint."""
            if body is not None:
                input_text = body.input
                voice = body.voice
                response_format = body.response_format
                speed = body.speed

            if not input_text:
                raise HTTPException(status_code=400, detail="Field 'input' is required")

            audio_data, _ = self._generate(
                input_text,
                speaker=voice if voice != "default" else "Sohee",
                speed=speed,
            )

            return StreamingResponse(
                io.BytesIO(audio_data),
                media_type=f"audio/{response_format}",
            )

    def load_model(self):
        """Load Qwen3-TTS model."""
        print(f"[*] Loading TTS model: {self._model_id}")

        try:
            from qwen_tts import Qwen3TTSModel

            self.tts_model = Qwen3TTSModel(self._model_id)
            print(f"[+] Qwen3-TTS loaded on CUDA")
        except ImportError:
            print("[!] qwen-tts not installed. Run: pip install qwen-tts")
            raise
        except Exception as e:
            print(f"[!] Model loading error: {e}")
            raise

    def _generate(
        self, text: str, speaker: str = "Sohee", speed: float = 1.0
    ) -> tuple[bytes, Optional[float]]:
        """Generate speech audio."""
        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            output_path = f.name

        try:
            self.tts_model.synthesize(
                text=text,
                speaker=speaker,
                speed=speed,
                output=output_path,
            )

            with open(output_path, "rb") as f:
                audio_data = f.read()

            try:
                info = sf.info(output_path)
                duration = info.duration
            except Exception:
                duration = None

            return audio_data, duration
        finally:
            Path(output_path).unlink(missing_ok=True)

    def _generate_clone(
        self,
        text: str,
        ref_audio_path: str,
        ref_text: Optional[str] = None,
    ) -> tuple[bytes, Optional[float]]:
        """Generate speech with voice cloning."""
        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            output_path = f.name

        try:
            kwargs = {
                "text": text,
                "reference_audio": ref_audio_path,
                "output": output_path,
            }
            if ref_text:
                kwargs["reference_text"] = ref_text

            self.tts_model.clone(**kwargs)

            with open(output_path, "rb") as f:
                audio_data = f.read()

            try:
                info = sf.info(output_path)
                duration = info.duration
            except Exception:
                duration = None

            return audio_data, duration
        finally:
            Path(output_path).unlink(missing_ok=True)


def main():
    args = CUDATTSWorker.parse_args()
    worker = CUDATTSWorker(
        alias=args.alias,
        model_path=args.model_path,
        port=args.port,
    )
    worker.run()


if __name__ == "__main__":
    main()
