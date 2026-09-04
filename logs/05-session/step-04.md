# Session 05 — Step 04: Voice Route Endpoint

**What was done:**
- Created `app/api_gateway/routes/voice.py` with two endpoints:
  - `POST /voice/chat` — full voice-to-voice weather pipeline
  - `GET /voice/languages` — list supported languages

**POST /voice/chat flow:**
1. **Validate** — audio size (≤10MB), format (wav/mp3/flac/ogg/m4a/webm/aac), language code
2. **ASR** — Bhashini speech-to-text (fallback: Groq Whisper)
3. **NMT inbound** — translate to English if lang ∉ {en, hi} (Hindi goes direct to LLM)
4. **LLM Chat** — existing `router.chat()` with tool-calling loop
5. **NMT outbound** — translate reply back to user's language if needed
6. **TTS** — synthesise audio response (optional, controlled by `response_format`)
7. **Return** — VoiceChatResponse with transcript, text, and optional base64 audio

**Request format:** multipart/form-data with fields: audio (file), language, session_id, response_format
**Graceful degradation:** Each NMT/TTS step catches exceptions and falls through (text-only response)

**Design decisions:**
- Hindi bypasses NMT — LLM system prompt already handles Hindi natively
- Empty ASR results return 422, not 200 with empty transcript
- Audio validation before any API calls to fail fast
