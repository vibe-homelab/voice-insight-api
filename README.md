# Voice Insight API

Mac Mini M4 (Apple Silicon)에서 MLX 가속을 활용한 로컬 음성 AI API 서버입니다.

## 기능

| 태스크 | 엔드포인트 | 설명 |
|--------|-----------|------|
| Audio → Text | `POST /v1/audio/transcriptions` | 음성을 텍스트로 변환 (OpenAI 호환) |
| Audio → Text | `POST /v1/transcribe` | Base64 오디오 변환 |
| Text → Audio | `POST /v1/audio/speech` | 텍스트를 음성으로 변환 (OpenAI 호환) |
| Text → Audio | `POST /v1/synthesize` | Base64 응답 음성 합성 |

## 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│  Docker                                                  │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Gateway (:8200) - FastAPI                       │    │
│  └──────────────────────┬──────────────────────────┘    │
└─────────────────────────┼───────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────┐
│  Host (macOS)           │                               │
│  ┌──────────────────────▼──────────────────────────┐    │
│  │  Worker Manager (:8210)                          │    │
│  │  - 워커 자동 스폰/종료                            │    │
│  │  - 메모리 관리                                   │    │
│  │  - Idle timeout (5분) 후 자동 offload            │    │
│  └──────────────────────┬──────────────────────────┘    │
│           ┌─────────────┼─────────────┐                 │
│           ▼             ▼             ▼                 │
│     ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│     │ stt-fast │  │ stt-best │  │ tts-fast │           │
│     │ :8211    │  │ :8212    │  │ :8213    │           │
│     │ Whisper  │  │ Whisper  │  │ Kokoro   │           │
│     │ Turbo    │  │ Large V3 │  │ 82M      │           │
│     └──────────┘  └──────────┘  └──────────┘           │
│              MLX / Metal Acceleration                   │
└─────────────────────────────────────────────────────────┘
```

## 빠른 시작

### 설치

```bash
# uv 설치 (없는 경우)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 의존성 설치
make install-worker

# 서비스 설치 및 시작
make service-install
make service-start

# Gateway 시작
make start
```

### 사용

```bash
# STT (음성 → 텍스트)
curl -X POST http://localhost:8200/v1/audio/transcriptions \
  -F "file=@audio.wav" \
  -F "model=stt-fast"

# TTS (텍스트 → 음성)
curl -X POST http://localhost:8200/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"input": "안녕하세요!", "model": "tts-fast"}' \
  --output output.wav

# 시스템 상태
curl http://localhost:8200/v1/system/status
```

---

## API Reference

### 1. 음성 인식 (Audio → Text)

**`POST /v1/audio/transcriptions`** (OpenAI 호환)

오디오 파일을 텍스트로 변환합니다.

#### Request

```bash
curl -X POST http://localhost:8200/v1/audio/transcriptions \
  -F "file=@audio.wav" \
  -F "model=stt-fast" \
  -F "language=ko"
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `file` | file | (필수) | 오디오 파일 (wav, mp3, m4a, webm, flac) |
| `model` | string | "stt-fast" | 모델 (`stt-fast`=빠름, `stt-best`=고품질) |
| `language` | string | auto | 언어 코드 (ko, en, ja 등) |

#### Response

```json
{
  "text": "안녕하세요, 반갑습니다.",
  "language": "ko",
  "duration": 3.5
}
```

---

### 2. 음성 합성 (Text → Audio)

**`POST /v1/audio/speech`** (OpenAI 호환)

텍스트를 음성으로 변환합니다.

#### Request

```json
{
  "input": "안녕하세요, 반갑습니다.",
  "model": "tts-fast",
  "voice": "af_heart",
  "speed": 1.0
}
```

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `input` | string | (필수) | 변환할 텍스트 |
| `model` | string | "tts-fast" | 모델 (`tts-fast`, `tts-stream`) |
| `voice` | string | "af_heart" | 음성 종류 |
| `speed` | float | 1.0 | 재생 속도 (0.5~2.0) |

#### Response

오디오 스트림 (audio/wav)

---

### 3. Base64 변환

**`POST /v1/transcribe`** - Base64 오디오 입력

```json
{
  "audio_base64": "<base64 encoded audio>",
  "model": "stt-fast",
  "language": "ko"
}
```

**`POST /v1/synthesize`** - Base64 오디오 출력

```json
{
  "text": "안녕하세요",
  "model": "tts-fast",
  "voice": "af_heart"
}
```

Response:
```json
{
  "audio_base64": "UklGRv...",
  "format": "wav",
  "duration": 1.5
}
```

---

### 4. 시스템 관리

| 엔드포인트 | 설명 |
|-----------|------|
| `GET /v1/models` | 모델 목록 |
| `GET /v1/voices` | 사용 가능한 음성 목록 |
| `GET /v1/system/status` | 시스템 상태 (메모리, 워커) |
| `POST /v1/system/evict/{alias}` | 워커 수동 종료 |
| `GET /healthz` | 헬스체크 |

---

## 모델 정보

| 별칭 | 모델 | 용도 | 메모리 |
|------|------|------|--------|
| `stt-fast` | Whisper Large V3 Turbo | 빠른 음성 인식 | ~1.5GB |
| `stt-best` | Whisper Large V3 | 고품질 음성 인식 | ~3GB |
| `tts-fast` | Kokoro 82M | 빠른 음성 합성 | ~0.5GB |
| `tts-stream` | Marvis TTS 250M | 스트리밍 음성 합성 | ~1GB |

---

## 음성 종류

| Voice ID | 설명 |
|----------|------|
| `af_heart` | 여성 (기본) |
| `af_bella` | 여성 |
| `af_sarah` | 여성 |
| `am_adam` | 남성 |
| `am_michael` | 남성 |
| `bf_emma` | 영국 여성 |
| `bm_george` | 영국 남성 |

---

## 관리 명령어

```bash
make install-worker   # MLX 의존성 설치
make service-install  # Worker Manager 서비스 설치
make service-start    # Worker Manager 시작
make start            # Gateway 시작
make stop             # Gateway 중지
make status           # 상태 확인
make logs             # Gateway 로그
make logs-manager     # Worker Manager 로그
make download-models  # 모델 미리 다운로드
```

---

## 설정

`config.yaml`에서 모델과 메모리 설정을 변경할 수 있습니다.

### 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `IDLE_TIMEOUT` | 300 | 워커 자동 종료 시간 (초) |
| `MANAGER_PORT` | 8210 | Worker Manager 포트 |

### 인증 (선택)

`config.yaml`의 `gateway.api_key`를 비워두면 인증 없이 동작합니다.
`gateway.api_key`를 설정하면 `/v1/*` 요청에 대해 다음 헤더 중 하나가 필요합니다.

- `Authorization: Bearer <api_key>`
- `X-API-Key: <api_key>`

---

## 라이선스

MIT
