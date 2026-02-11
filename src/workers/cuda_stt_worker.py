"""
CUDA STT Worker - Voxtral Mini 4B Realtime speech-to-text via vLLM.

This worker launches a vLLM server for Voxtral and proxies transcription requests.
The vLLM server exposes an OpenAI-compatible /v1/chat/completions endpoint
that accepts audio input.

Requires: vllm, soxr, librosa, soundfile
"""

import base64
import io
import os
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


class CUDASTTWorker(BaseWorker):
    """Speech-to-Text worker using Voxtral Mini 4B on NVIDIA GPU via vLLM."""

    def __init__(self, alias: str, model_path: str, port: int, **params):
        super().__init__(alias, model_path, port)
        self.params = params
        self._vllm_port = port  # vLLM server runs on this port
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
            """Transcribe audio to text using Voxtral."""
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

                # Convert audio to base64 for Voxtral's chat API
                audio_b64 = base64.b64encode(audio_data).decode()

                # Call vLLM's OpenAI-compatible endpoint
                import httpx

                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "audio_url",
                                "audio_url": {
                                    "url": f"data:audio/wav;base64,{audio_b64}",
                                },
                            },
                            {
                                "type": "text",
                                "text": "Transcribe this audio accurately.",
                            },
                        ],
                    }
                ]

                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(
                        f"http://localhost:{self._vllm_port}/v1/chat/completions",
                        json={
                            "model": self.model_path,
                            "messages": messages,
                            "max_tokens": 4096,
                            "temperature": 0,
                        },
                    )
                    resp.raise_for_status()
                    result = resp.json()

                text = result["choices"][0]["message"]["content"]

                return TranscriptionResponse(
                    text=text.strip(),
                    language=language,
                )

            except httpx.HTTPError as e:
                raise HTTPException(status_code=502, detail=f"vLLM server error: {e}")
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
            audio_b64 = base64.b64encode(audio_data).decode()

            # Reuse internal transcribe logic
            import httpx

            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "audio_url",
                            "audio_url": {
                                "url": f"data:audio/wav;base64,{audio_b64}",
                            },
                        },
                        {
                            "type": "text",
                            "text": "Transcribe this audio accurately.",
                        },
                    ],
                }
            ]

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"http://localhost:{self._vllm_port}/v1/chat/completions",
                    json={
                        "model": self.model_path,
                        "messages": messages,
                        "max_tokens": 4096,
                        "temperature": 0,
                    },
                )
                resp.raise_for_status()
                result = resp.json()

            text = result["choices"][0]["message"]["content"].strip()

            if response_format == "text":
                return text
            return {"text": text}

    def load_model(self):
        """
        For CUDA STT, the model is served by vLLM externally.
        This worker acts as a proxy adapter providing the standard STT API
        on top of vLLM's chat completions endpoint.

        When used with the homelab-dashboard orchestrator, the orchestrator
        starts vLLM serve as the main process. This worker wraps it with
        the STT-specific API endpoints.
        """
        print(f"[*] CUDA STT Worker ready (Voxtral proxy on port {self._vllm_port})")
        print(f"[*] Model: {self.model_path}")
        print(f"[*] Expects vLLM server at localhost:{self._vllm_port}")


def main():
    args = CUDASTTWorker.parse_args()
    worker = CUDASTTWorker(
        alias=args.alias,
        model_path=args.model_path,
        port=args.port,
    )
    worker.run()


if __name__ == "__main__":
    main()
