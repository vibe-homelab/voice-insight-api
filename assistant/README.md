# Voice Assistant

STT -> LLM -> TTS 음성 어시스턴트 파이프라인 오케스트레이션 서비스.

기존 **Voice Insight API**(STT/TTS)와 **Language Insight API**(LLM)를 연결하여 end-to-end 음성 대화를 구현합니다.

## 아키텍처

```
┌───────────┐     ┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌──────────┐
│ Microphone│────>│ Voice API (STT) │────>│ Language API (LLM)│────>│ Voice API (TTS) │────>│ Speaker  │
│           │     │ :8200           │     │ :8400             │     │ :8200           │     │          │
└───────────┘     └─────────────────┘     └──────────────────┘     └─────────────────┘     └──────────┘
                       ~100-200ms              ~200-400ms                ~100-200ms
```

**예상 총 지연 시간**: 450-750ms (모델 및 입력 길이에 따라 달라짐)

## 빠른 시작

### 로컬 실행

```bash
# 의존성 설치
pip install -e .

# 설정 파일 수정 (필요한 경우)
vim config.yaml

# 서버 실행
python -m src.gateway.main
```

### Docker 실행

```bash
docker compose up -d
```

서비스가 `http://localhost:8800`에서 시작됩니다.

## API 레퍼런스

### 헬스 체크

```bash
# 전체 서비스 상태
curl http://localhost:8800/healthz

# 각 서비스 지연 시간
curl http://localhost:8800/v1/pipeline/status
```

### 음성 대화 (Full Pipeline: Audio -> Audio)

```bash
curl -X POST http://localhost:8800/v1/voice/chat \
  -F "file=@input.wav" \
  -F "session_id=my-session" \
  --output response.wav
```

응답 헤더:
- `X-Transcription`: STT 결과 (URL-encoded)
- `X-Response-Text`: LLM 응답 (URL-encoded)
- `X-Session-Id`: 세션 ID

### 텍스트 대화 (Text -> Audio, STT 생략)

```bash
curl -X POST http://localhost:8800/v1/voice/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "오늘 날씨 어때?", "session_id": "my-session"}' \
  --output response.wav
```

### 음성 질문 (Audio -> Text, TTS 생략)

```bash
curl -X POST http://localhost:8800/v1/voice/listen \
  -F "file=@input.wav" \
  -F "session_id=my-session"
```

응답:
```json
{
  "transcription": "오늘 날씨 어때?",
  "response": "오늘은 맑고 기온이 15도 정도입니다.",
  "session_id": "my-session"
}
```

### 세션 관리

```bash
# 대화 기록 조회
curl http://localhost:8800/v1/sessions/my-session

# 대화 기록 삭제
curl -X DELETE http://localhost:8800/v1/sessions/my-session
```

## 설정

`config.yaml`에서 서비스 엔드포인트, 모델, 파이프라인 설정을 변경할 수 있습니다.

| 항목 | 설명 | 기본값 |
|------|------|--------|
| `services.stt.endpoint` | Voice Insight API 주소 | `http://localhost:8200` |
| `services.stt.model` | STT 모델 | `stt-fast` |
| `services.llm.endpoint` | Language Insight API 주소 | `http://localhost:8400` |
| `services.llm.model` | LLM 모델 | `llm-small` |
| `services.tts.voice` | TTS 음성 | `af_heart` |
| `pipeline.port` | 서비스 포트 | `8800` |
| `pipeline.conversation_history_limit` | 세션당 대화 기록 수 | `10` |
