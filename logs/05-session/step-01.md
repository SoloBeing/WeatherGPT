# Session 05 — Step 01: Config & Dependencies

**What was done:**
- Added Bhashini ULCA pipeline settings to `app/config.py`:
  - `BHASHINI_ULCA_CONFIG_URL` (ULCA model discovery endpoint)
  - `BHASHINI_PIPELINE_ID` (default master pipeline `64392f96daac500b55c543cd`)
  - `BHASHINI_TTS_GENDER` (default `female`)
  - `GROQ_WHISPER_MODEL` (fallback ASR via Groq, default `whisper-large-v3`)
- Added `python-multipart>=0.0.20` and `gtts>=2.5.4` to `pyproject.toml`
- Appended Bhashini ULCA config settings to `.env`
- Updated `GEMINI.md` session log convention to mandate writing step logs before proceeding
- Ran `uv sync` — all deps installed successfully

**Commands:**
```bash
# Append Bhashini settings to .env
cat >> .env << 'ENVEOF'
BHASHINI_ULCA_CONFIG_URL=https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline
BHASHINI_PIPELINE_ID=64392f96daac500b55c543cd
BHASHINI_TTS_GENDER=female
GROQ_WHISPER_MODEL=whisper-large-v3
ENVEOF

# Install new deps
uv sync
```

**Notable output:**
- `python-multipart==0.0.32` installed (FastAPI UploadFile support)
- `gtts` pulled in as fallback TTS
