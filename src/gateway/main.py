"""Voice Insight API Gateway."""

import base64
import io
from typing import Any, Dict, List, Optional

import httpx
import uvicorn
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from src.core.config import get_config
from src.core.supervisor import Supervisor

_DEFAULT_API_KEYS = {"default-key", "default-key-change-me"}
_config = get_config()

MAX_UPLOAD_SIZE_MB = 500
MAX_TTS_INPUT_LENGTH = 10000


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


class OpenAISpeechRequest(BaseModel):
    """OpenAI-compatible Text-to-Speech request body."""

    model: str = "tts-fast"
    input: str
    voice: str = "af_heart"
    response_format: str = "wav"
    speed: float = 1.0


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

import asyncio
import logging
import time
import uuid

logger = logging.getLogger(__name__)


async def _get_worker_or_fail(alias: str):
    """Get worker with friendly cold-start error handling."""
    try:
        return await supervisor.get_worker(alias)
    except MemoryError as e:
        raise HTTPException(
            status_code=507,
            detail={
                "error": "insufficient_memory",
                "message": str(e),
                "hint": "Evict unused models via POST /v1/system/evict/{alias}",
            },
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "service_unavailable",
                "message": str(e),
                "hint": "Worker Manager may not be running. Check: curl http://localhost:8210/health",
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "worker_startup_failed",
                "message": f"Model loading failed: {e}",
                "hint": "Model may still be downloading or loading. Retry in 30-60 seconds.",
            },
        )


@app.middleware("http")
async def request_logging_middleware(request, call_next):
    request_id = uuid.uuid4().hex[:8]
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - start) * 1000, 1)
    logger.info(
        "%s %s %s %sms [%s]",
        request.method, request.url.path, response.status_code, duration_ms, request_id
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def api_key_auth_middleware(request, call_next):
    """Optional API key auth for all /v1/* endpoints.

    Enable by setting `gateway.api_key` in `config.yaml` to a non-empty value.
    Clients may send either:
    - Authorization: Bearer <api_key>
    - X-API-Key: <api_key>
    """
    path = request.url.path
    if not path.startswith("/v1/"):
        return await call_next(request)

    api_key = (_config.gateway.api_key or "").strip()
    if not api_key or api_key in _DEFAULT_API_KEYS:
        return await call_next(request)

    auth = request.headers.get("authorization", "")
    provided = ""
    if auth.lower().startswith("bearer "):
        provided = auth.split(" ", 1)[1].strip()
    if not provided:
        provided = (request.headers.get("x-api-key", "") or "").strip()

    if provided != api_key:
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    return await call_next(request)


# Health & Status
@app.get("/healthz")
async def healthz():
    try:
        connected = await supervisor.health_check()
        if connected:
            return {"status": "ok", "supervisor": "connected"}
    except Exception:
        pass
    return {"status": "degraded", "supervisor": "disconnected"}


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
        manager_status = await supervisor.get_status()
    except Exception:
        manager_status = {"workers": {}, "memory": {}}

    # Add model availability info
    config = get_config()
    loaded = set(manager_status.get("workers", {}).keys())
    models_status = {}
    for alias, model_cfg in config.models.items():
        if model_cfg.backend != "mlx":
            continue
        models_status[alias] = {
            "path": model_cfg.path,
            "status": "loaded" if alias in loaded else "unloaded",
            "memory_gb": model_cfg.parsed_params.memory_gb,
        }

    return {
        **manager_status,
        "models": models_status,
    }


@app.post("/v1/system/warm/{alias}")
async def warm_model(alias: str):
    """Trigger model loading in background without waiting. Returns immediately."""
    config = get_config()
    if alias not in config.models:
        raise HTTPException(status_code=404, detail=f"Unknown model: {alias}")

    async def _warm():
        try:
            await supervisor.get_worker(alias)
        except Exception as e:
            logger.warning("Warm-up failed for %s: %s", alias, e)

    asyncio.create_task(_warm())
    return {
        "status": "warming",
        "alias": alias,
        "model": config.models[alias].path,
        "estimated_seconds": 30,
        "hint": "Check GET /v1/system/status to see when ready",
    }


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
    # Validate file size
    if file.size is not None and file.size > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum upload size is {MAX_UPLOAD_SIZE_MB} MB.",
        )

    # Get worker
    worker = await _get_worker_or_fail(model)

    # Forward request
    audio_data = await file.read()

    # Check actual size if file.size was not available
    if len(audio_data) > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum upload size is {MAX_UPLOAD_SIZE_MB} MB.",
        )
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
    worker = await _get_worker_or_fail(request.model)

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
    body: OpenAISpeechRequest | None = Body(default=None),
    model: str = Query(default="tts-fast"),
    input_text: str = Query(default="", alias="input"),
    voice: str = Query(default="af_heart"),
    response_format: str = Query(default="wav"),
    speed: float = Query(default=1.0),
):
    """
    Generate speech from text (OpenAI-compatible).

    Returns audio stream.
    """
    if body is not None:
        model = body.model
        input_text = body.input
        voice = body.voice
        response_format = body.response_format
        speed = body.speed

    if not input_text:
        raise HTTPException(status_code=400, detail="Field 'input' is required")

    if len(input_text) > MAX_TTS_INPUT_LENGTH:
        raise HTTPException(
            status_code=413,
            detail=f"Input text too long. Maximum length is {MAX_TTS_INPUT_LENGTH} characters.",
        )

    worker = await _get_worker_or_fail(model)

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{worker.address}/synthesize",
            json={
                "text": input_text,
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
    worker = await _get_worker_or_fail(request.model)

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
        worker = await _get_worker_or_fail(model)

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
