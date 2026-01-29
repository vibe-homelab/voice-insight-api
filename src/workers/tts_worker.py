"""Text-to-Speech worker using MLX Audio."""

import base64
import io
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .base import BaseWorker


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None
    speed: float = 1.0
    format: str = "wav"  # wav, mp3
    stream: bool = False


class TTSResponse(BaseModel):
    audio_base64: str
    format: str
    duration: Optional[float] = None


class TTSWorker(BaseWorker):
    """Text-to-Speech worker using mlx-audio."""

    def __init__(self, alias: str, model_path: str, port: int, **params):
        super().__init__(alias, model_path, port)
        self.params = params
        self.default_voice = params.get("voice", "af_heart")
        self.default_speed = params.get("speed", 1.0)
        self.model = None
        self._setup_tts_routes()

    def _setup_tts_routes(self):
        """Setup TTS-specific routes."""

        @self.app.post("/synthesize")
        async def synthesize(request: TTSRequest):
            """Synthesize speech from text."""
            try:
                voice = request.voice or self.default_voice
                speed = request.speed or self.default_speed

                if request.stream:
                    # Streaming response
                    return StreamingResponse(
                        self._stream_audio(request.text, voice, speed),
                        media_type="audio/wav",
                    )

                # Non-streaming response
                audio_data, duration = self._generate_audio(
                    request.text,
                    voice=voice,
                    speed=speed,
                    format=request.format,
                )

                return TTSResponse(
                    audio_base64=base64.b64encode(audio_data).decode(),
                    format=request.format,
                    duration=duration,
                )

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/v1/audio/speech")
        async def openai_speech(
            model: str = "tts-1",
            input: str = "",
            voice: str = "alloy",
            response_format: str = "wav",
            speed: float = 1.0,
        ):
            """OpenAI-compatible speech endpoint."""
            try:
                # Map OpenAI voices to available voices
                mapped_voice = self._map_voice(voice)

                audio_data, _ = self._generate_audio(
                    input,
                    voice=mapped_voice,
                    speed=speed,
                    format=response_format,
                )

                return StreamingResponse(
                    io.BytesIO(audio_data),
                    media_type=f"audio/{response_format}",
                )

            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/voices")
        async def list_voices():
            """List available voices."""
            return {"voices": self._get_available_voices()}

    def load_model(self):
        """Load TTS model using mlx-audio."""
        print(f"Loading TTS model: {self.model_path}")

        try:
            from mlx_audio.tts import generate as mlx_generate
            from mlx_audio.tts import stream as mlx_stream

            self._generate_fn = mlx_generate
            self._stream_fn = mlx_stream
            self._backend = "mlx_audio"
            print(f"Using mlx_audio TTS backend for {self.model_path}")
        except ImportError:
            raise RuntimeError(
                "mlx-audio not installed. Run: pip install mlx-audio"
            )

        print(f"TTS model loaded successfully: {self.alias}")

    def _generate_audio(
        self,
        text: str,
        voice: str,
        speed: float = 1.0,
        format: str = "wav",
    ) -> tuple[bytes, Optional[float]]:
        """Generate audio from text."""
        with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as f:
            output_path = f.name

        try:
            # Generate audio using mlx_audio
            self._generate_fn(
                text=text,
                model=self.model_path,
                voice=voice,
                speed=speed,
                output=output_path,
            )

            # Read generated audio
            with open(output_path, "rb") as f:
                audio_data = f.read()

            # Calculate duration (approximate)
            duration = None
            try:
                import soundfile as sf
                info = sf.info(output_path)
                duration = info.duration
            except Exception:
                pass

            return audio_data, duration

        finally:
            Path(output_path).unlink(missing_ok=True)

    async def _stream_audio(self, text: str, voice: str, speed: float):
        """Stream audio chunks."""
        try:
            for chunk in self._stream_fn(
                text=text,
                model=self.model_path,
                voice=voice,
                speed=speed,
            ):
                yield chunk
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    def _map_voice(self, openai_voice: str) -> str:
        """Map OpenAI voice names to available voices."""
        voice_map = {
            "alloy": "af_heart",
            "echo": "am_adam",
            "fable": "bf_emma",
            "onyx": "am_michael",
            "nova": "af_sarah",
            "shimmer": "af_bella",
        }
        return voice_map.get(openai_voice, self.default_voice)

    def _get_available_voices(self) -> list[str]:
        """Get list of available voices."""
        # Common Kokoro voices
        return [
            "af_heart",
            "af_bella",
            "af_sarah",
            "af_nicole",
            "am_adam",
            "am_michael",
            "bf_emma",
            "bf_isabella",
            "bm_george",
            "bm_lewis",
        ]


def main():
    args = TTSWorker.parse_args()
    worker = TTSWorker(
        alias=args.alias,
        model_path=args.model_path,
        port=args.port,
    )
    worker.run()


if __name__ == "__main__":
    main()
