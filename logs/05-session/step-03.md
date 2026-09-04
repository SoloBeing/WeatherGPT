# Session 05 — Step 03: Voice Schemas

**What was done:**
- Added `VoiceChatResponse` Pydantic model to `app/schemas_and_models/schemas.py`
- Fields: `transcript_in`, `reply_text`, `reply_audio_base64` (optional), `language`, `session_id`, `sources`
- No separate `VoiceChatRequest` model needed — voice endpoint uses FastAPI's `UploadFile` + `Form` fields directly from multipart form data

**Design decisions:**
- `reply_audio_base64` is Optional — allows `response_format=text` to skip TTS entirely
- Reuses `sources` list pattern from `ChatResponse` for consistency
- `transcript_in` included so frontend can display what was heard (important for user trust)
