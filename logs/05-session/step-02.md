# Session 05 — Step 02: Bhashini API Client

**What was done:**
- Replaced empty `app/external_services/bhashini.py` stub with full ULCA client
- Class `BhashiniService` with methods:
  - `_discover_pipeline()` — POST to ULCA config endpoint, caches serviceIds + inference JWT for 1 hour
  - `_ensure_pipeline()` — lazy init with TTL check
  - `asr(audio_bytes, source_lang, audio_format, sampling_rate)` → transcribed text
  - `translate(text, source_lang, target_lang)` → translated text
  - `tts(text, target_lang, gender)` → WAV audio bytes
  - `_groq_whisper_fallback()` — uses Groq Whisper via litellm.atranscription
  - `_gtts_fallback()` — uses gTTS library for basic speech synthesis
- Sandbox mode: if BHASHINI_API_KEY is empty, logs calls and returns mocks
- Auto-retry on 401 (expired inference token → re-discover pipeline)
- `SUPPORTED_LANGUAGES` dict with all 22 Scheduled Languages + English
- Module-level singleton `bhashini_service` for import

**Design decisions:**
- Follows same service-class + sandbox pattern as FCMService
- Uses httpx.AsyncClient (connection-pooled, 30s timeout)
- Pipeline config cached in-memory with timestamp (not Redis) — lightweight, per-process
- NMT gracefully degrades to returning original text on failure
- ASR falls back to Groq Whisper (already have Groq API key)
- TTS falls back to gTTS (offline, no API key needed)
