"""Voice Insight API Gateway."""

import base64
import io
from typing import Any, Dict, List, Optional

import httpx
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.core.config import get_config
from src.core.supervisor import Supervisor


# Request/Response Models
class TranscriptionRequest(BaseModel):
    audio_base64: str
    model: str = "stt-fast"
    language: Optional[str] = None
    task: str = "transcribe"  # transcribe or translate


class TranscriptionResponse(BaseModel):
    text: str
    language: Optional[str] = None
    duration: Optional[float] = None


class SpeechRequest(BaseModel):
    text: str
    model: str = "tts-fast"
    voice: Optional[str] = None
    speed: float = 1.0
    format: str = "wav"


class SpeechResponse(BaseModel):
    audio_base64: str
    format: str
    duration: Optional[float] = None


class ModelInfo(BaseModel):
    id: str
    type: str
    path: str


# FastAPI App
app = FastAPI(
    title="Voice Insight API",
    description="Self-hosted STT/TTS API optimized for Apple Silicon",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

supervisor = Supervisor()


# Health & Status
@app.get("/healthz")
async def healthz():
    return {"status": "healthy"}


@app.get("/v1/models")
async def list_models() -> Dict[str, List[ModelInfo]]:
    """List available models."""
    config = get_config()
    models = []
    for alias, model_config in config.models.items():
        models.append(
            ModelInfo(
                id=alias,
                type=model_config.type,
                path=model_config.path,
            )
        )
    return {"data": models}


@app.get("/v1/system/status")
async def system_status():
    """Get system and worker status."""
    try:
        return await supervisor.get_status()
    except Exception as e:
        return {"error": str(e)}


@app.post("/v1/system/evict/{alias}")
async def evict_worker(alias: str):
    """Manually evict a worker."""
    success = await supervisor.stop_worker(alias)
    return {"success": success}


# STT Endpoints
@app.post("/v1/audio/transcriptions", response_model=TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Form("stt-fast"),
    language: Optional[str] = Form(None),
):
    """
    Transcribe audio file (OpenAI-compatible).

    Supported formats: wav, mp3, m4a, webm, flac
    """
    # Get worker
    worker = await supervisor.get_worker(model)

    # Forward request
    audio_data = await file.read()
    audio_b64 = base64.b64encode(audio_data).decode()

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{worker.address}/transcribe",
            data={
                "audio_base64": audio_b64,
                "language": language or "",
                "task": "transcribe",
            },
        )

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.text)

        result = response.json()
        return TranscriptionResponse(**result)


@app.post("/v1/transcribe", response_model=TranscriptionResponse)
async def transcribe_base64(request: TranscriptionRequest):
    """Transcribe audio from base64."""
    worker = await supervisor.get_worker(request.model)

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{worker.address}/transcribe",
            data={
                "audio_base64": request.audio_base64,
                "language": request.language or "",
                "task": request.task,
            },
        )

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.text)

        return TranscriptionResponse(**response.json())


# TTS Endpoints
@app.post("/v1/audio/speech")
async def create_speech(
    model: str = "tts-fast",
    input: str = "",
    voice: str = "af_heart",
    response_format: str = "wav",
    speed: float = 1.0,
):
    """
    Generate speech from text (OpenAI-compatible).

    Returns audio stream.
    """
    worker = await supervisor.get_worker(model)

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{worker.address}/synthesize",
            json={
                "text": input,
                "voice": voice,
                "speed": speed,
                "format": response_format,
                "stream": False,
            },
        )

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.text)

        result = response.json()
        audio_data = base64.b64decode(result["audio_base64"])

        return StreamingResponse(
            io.BytesIO(audio_data),
            media_type=f"audio/{response_format}",
        )


@app.post("/v1/synthesize", response_model=SpeechResponse)
async def synthesize_speech(request: SpeechRequest):
    """Generate speech from text (returns base64)."""
    worker = await supervisor.get_worker(request.model)

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{worker.address}/synthesize",
            json={
                "text": request.text,
                "voice": request.voice,
                "speed": request.speed,
                "format": request.format,
                "stream": False,
            },
        )

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=response.text)

        return SpeechResponse(**response.json())


@app.get("/v1/voices")
async def list_voices(model: str = "tts-fast"):
    """List available voices for a TTS model."""
    try:
        worker = await supervisor.get_worker(model)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{worker.address}/voices")
            return response.json()
    except Exception:
        # Return default voices if worker not available
        return {
            "voices": [
                "af_heart",
                "af_bella",
                "af_sarah",
                "am_adam",
                "am_michael",
                "bf_emma",
                "bm_george",
            ]
        }


def main():
    config = get_config()
    uvicorn.run(
        "src.gateway.main:app",
        host=config.gateway.host,
        port=config.gateway.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
