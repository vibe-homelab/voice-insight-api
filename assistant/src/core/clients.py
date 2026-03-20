"""HTTP clients for Voice Insight API (STT/TTS) and Language Insight API (LLM)."""

from __future__ import annotations

import httpx


class STTClient:
    """Client for Voice Insight API speech-to-text."""

    def __init__(self, endpoint: str, timeout: float = 30.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    async def transcribe(
        self,
        audio_data: bytes,
        model: str,
        language: str | None = None,
    ) -> str:
        """Send audio to the STT endpoint and return transcribed text."""
        files = {"file": ("audio.wav", audio_data, "audio/wav")}
        data: dict[str, str] = {"model": model}
        if language:
            data["language"] = language

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.endpoint}/v1/audio/transcriptions",
                files=files,
                data=data,
            )
            resp.raise_for_status()
            return resp.json()["text"]

    async def health(self) -> bool:
        """Return True if the STT service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.endpoint}/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False


class LLMClient:
    """Client for Language Insight API."""

    def __init__(self, endpoint: str, timeout: float = 60.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    async def chat(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int = 256,
        temperature: float = 0.7,
    ) -> str:
        """Send chat messages and return the assistant response text."""
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.endpoint}/v1/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

    async def health(self) -> bool:
        """Return True if the LLM service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.endpoint}/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False


class TTSClient:
    """Client for Voice Insight API text-to-speech."""

    def __init__(self, endpoint: str, timeout: float = 30.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    async def synthesize(
        self,
        text: str,
        model: str,
        voice: str = "af_heart",
        speed: float = 1.0,
    ) -> bytes:
        """Send text to the TTS endpoint and return audio bytes (WAV)."""
        payload = {
            "model": model,
            "input": text,
            "voice": voice,
            "speed": speed,
            "response_format": "wav",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.endpoint}/v1/audio/speech",
                json=payload,
            )
            resp.raise_for_status()
            return resp.content

    async def health(self) -> bool:
        """Return True if the TTS service is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.endpoint}/health")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
