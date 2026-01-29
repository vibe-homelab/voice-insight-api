"""Speech-to-Text worker using MLX Whisper."""

import base64
import io
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
    segments: Optional[list] = None


class STTWorker(BaseWorker):
    """Speech-to-Text worker using mlx-audio/whisper."""

    def __init__(self, alias: str, model_path: str, port: int, **params):
        super().__init__(alias, model_path, port)
        self.params = params
        self.model = None
        self._setup_stt_routes()

    def _setup_stt_routes(self):
        """Setup STT-specific routes."""

        @self.app.post("/transcribe", response_model=TranscriptionResponse)
        async def transcribe(
            file: Optional[UploadFile] = File(None),
            audio_base64: Optional[str] = Form(None),
            language: Optional[str] = Form(None),
            task: str = Form("transcribe"),  # transcribe or translate
        ):
            """Transcribe audio to text."""
            if file is None and audio_base64 is None:
                raise HTTPException(
                    status_code=400,
                    detail="Either file or audio_base64 must be provided"
                )

            try:
                # Get audio data
                if file:
                    audio_data = await file.read()
                else:
                    audio_data = base64.b64decode(audio_base64)

                # Write to temp file (mlx-audio requires file path)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    f.write(audio_data)
                    temp_path = f.name

                try:
                    # Transcribe
                    result = self._transcribe(
                        temp_path,
                        language=language,
                        task=task,
                    )
                    return result
                finally:
                    # Cleanup
                    Path(temp_path).unlink(missing_ok=True)

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
                result = self._transcribe(temp_path, language=language)

                if response_format == "text":
                    return result.text
                return {"text": result.text}
            finally:
                Path(temp_path).unlink(missing_ok=True)

    def load_model(self):
        """Load Whisper model using mlx-audio."""
        print(f"Loading STT model: {self.model_path}")

        try:
            # Try mlx_audio first (recommended)
            from mlx_audio.stt import transcribe as mlx_transcribe
            self._transcribe_fn = mlx_transcribe
            self._backend = "mlx_audio"
            print(f"Using mlx_audio backend for {self.model_path}")
        except ImportError:
            try:
                # Fallback to mlx_whisper
                import mlx_whisper
                self._transcribe_fn = mlx_whisper.transcribe
                self._backend = "mlx_whisper"
                print(f"Using mlx_whisper backend for {self.model_path}")
            except ImportError:
                raise RuntimeError(
                    "No STT backend available. Install mlx-audio or mlx-whisper."
                )

        # Pre-warm the model by running a dummy transcription
        print(f"STT model loaded successfully: {self.alias}")

    def _transcribe(
        self,
        audio_path: str,
        language: Optional[str] = None,
        task: str = "transcribe",
    ) -> TranscriptionResponse:
        """Transcribe audio file."""
        kwargs = {"path_or_hf_repo": self.model_path}

        if language:
            kwargs["language"] = language

        if task == "translate":
            kwargs["task"] = "translate"

        if self._backend == "mlx_audio":
            # mlx_audio.stt.transcribe signature
            result = self._transcribe_fn(audio_path, **kwargs)
        else:
            # mlx_whisper.transcribe signature
            result = self._transcribe_fn(audio_path, **kwargs)

        # Normalize result format
        if isinstance(result, dict):
            return TranscriptionResponse(
                text=result.get("text", "").strip(),
                language=result.get("language"),
                duration=result.get("duration"),
                segments=result.get("segments"),
            )
        else:
            return TranscriptionResponse(text=str(result).strip())


def main():
    args = STTWorker.parse_args()
    worker = STTWorker(
        alias=args.alias,
        model_path=args.model_path,
        port=args.port,
    )
    worker.run()


if __name__ == "__main__":
    main()
