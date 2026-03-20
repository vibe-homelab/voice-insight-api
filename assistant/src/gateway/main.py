"""FastAPI gateway – voice assistant pipeline orchestration."""

from __future__ import annotations

import time
import urllib.parse
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from src.core.clients import LLMClient, STTClient, TTSClient
from src.core.config import AppConfig, load_config
from src.core.conversation import ConversationManager

# ---------------------------------------------------------------------------
# Globals (initialised in lifespan)
# ---------------------------------------------------------------------------
config: AppConfig
stt_client: STTClient
llm_client: LLMClient
tts_client: TTSClient
conversation: ConversationManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    global config, stt_client, llm_client, tts_client, conversation
    config = load_config()
    stt_client = STTClient(config.services.stt.endpoint)
    llm_client = LLMClient(config.services.llm.endpoint)
    tts_client = TTSClient(config.services.tts.endpoint)
    conversation = ConversationManager(
        system_prompt=config.services.llm.system_prompt,
        history_limit=config.pipeline.conversation_history_limit,
    )
    yield


app = FastAPI(
    title="Voice Assistant",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/healthz")
async def healthz():
    stt_ok = await stt_client.health()
    llm_ok = await llm_client.health()
    tts_ok = await tts_client.health()
    status = "healthy" if all([stt_ok, llm_ok, tts_ok]) else "degraded"
    return {
        "status": status,
        "services": {"stt": stt_ok, "llm": llm_ok, "tts": tts_ok},
    }


# ---------------------------------------------------------------------------
# Full pipeline: audio in -> audio out
# ---------------------------------------------------------------------------
@app.post("/v1/voice/chat")
async def voice_chat(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
):
    """Audio in, audio out.  STT -> LLM -> TTS."""
    if session_id is None:
        session_id = conversation.new_session()

    audio_data = await file.read()
    if not audio_data:
        raise HTTPException(status_code=400, detail="Empty audio file")

    # STT
    try:
        transcription = await stt_client.transcribe(
            audio_data,
            model=config.services.stt.model,
            language=config.services.stt.language,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"STT service error: {exc}")

    # LLM
    conversation.add_message(session_id, "user", transcription)
    messages = conversation.get_messages(session_id)
    try:
        response_text = await llm_client.chat(
            messages,
            model=config.services.llm.model,
            max_tokens=config.services.llm.max_tokens,
            temperature=config.services.llm.temperature,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"LLM service error: {exc}")
    conversation.add_message(session_id, "assistant", response_text)

    # TTS
    try:
        audio_out = await tts_client.synthesize(
            response_text,
            model=config.services.tts.model,
            voice=config.services.tts.voice,
            speed=config.services.tts.speed,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"TTS service error: {exc}")

    return Response(
        content=audio_out,
        media_type="audio/wav",
        headers={
            "X-Transcription": urllib.parse.quote(transcription),
            "X-Response-Text": urllib.parse.quote(response_text),
            "X-Session-Id": session_id,
        },
    )


# ---------------------------------------------------------------------------
# Text in -> audio out (skip STT)
# ---------------------------------------------------------------------------
class SpeakRequest(BaseModel):
    text: str
    session_id: Optional[str] = None


@app.post("/v1/voice/speak")
async def voice_speak(req: SpeakRequest):
    """Text in, audio out.  LLM -> TTS."""
    session_id = req.session_id or conversation.new_session()

    # LLM
    conversation.add_message(session_id, "user", req.text)
    messages = conversation.get_messages(session_id)
    try:
        response_text = await llm_client.chat(
            messages,
            model=config.services.llm.model,
            max_tokens=config.services.llm.max_tokens,
            temperature=config.services.llm.temperature,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"LLM service error: {exc}")
    conversation.add_message(session_id, "assistant", response_text)

    # TTS
    try:
        audio_out = await tts_client.synthesize(
            response_text,
            model=config.services.tts.model,
            voice=config.services.tts.voice,
            speed=config.services.tts.speed,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"TTS service error: {exc}")

    return Response(
        content=audio_out,
        media_type="audio/wav",
        headers={
            "X-Response-Text": urllib.parse.quote(response_text),
            "X-Session-Id": session_id,
        },
    )


# ---------------------------------------------------------------------------
# Audio in -> text out (skip TTS)
# ---------------------------------------------------------------------------
@app.post("/v1/voice/listen")
async def voice_listen(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
):
    """Audio in, text out.  STT -> LLM."""
    if session_id is None:
        session_id = conversation.new_session()

    audio_data = await file.read()
    if not audio_data:
        raise HTTPException(status_code=400, detail="Empty audio file")

    # STT
    try:
        transcription = await stt_client.transcribe(
            audio_data,
            model=config.services.stt.model,
            language=config.services.stt.language,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"STT service error: {exc}")

    # LLM
    conversation.add_message(session_id, "user", transcription)
    messages = conversation.get_messages(session_id)
    try:
        response_text = await llm_client.chat(
            messages,
            model=config.services.llm.model,
            max_tokens=config.services.llm.max_tokens,
            temperature=config.services.llm.temperature,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"LLM service error: {exc}")
    conversation.add_message(session_id, "assistant", response_text)

    return {
        "transcription": transcription,
        "response": response_text,
        "session_id": session_id,
    }


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------
@app.delete("/v1/sessions/{session_id}")
async def delete_session(session_id: str):
    conversation.clear(session_id)
    return {"status": "cleared", "session_id": session_id}


@app.get("/v1/sessions/{session_id}")
async def get_session(session_id: str):
    history = conversation.get_history(session_id)
    return {"session_id": session_id, "messages": history}


# ---------------------------------------------------------------------------
# Pipeline status
# ---------------------------------------------------------------------------
@app.get("/v1/pipeline/status")
async def pipeline_status():
    """Check latency of each backend service."""
    results: dict[str, dict] = {}
    for name, client in [
        ("stt", stt_client),
        ("llm", llm_client),
        ("tts", tts_client),
    ]:
        t0 = time.monotonic()
        ok = await client.health()
        latency_ms = round((time.monotonic() - t0) * 1000, 1)
        results[name] = {"healthy": ok, "latency_ms": latency_ms}
    return results


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    import uvicorn

    cfg = load_config()
    uvicorn.run(
        "src.gateway.main:app",
        host=cfg.pipeline.host,
        port=cfg.pipeline.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
