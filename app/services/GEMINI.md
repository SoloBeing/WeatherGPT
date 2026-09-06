# services — Context

## Role
Clients for third-party services that aren't weather data sources.

## Files
- `bhashini.py` — Bhashini ULCA APIs: ASR (speech→text), MT (translation), TTS (text→speech), 22 Indian languages
- `fcm.py` — Firebase Cloud Messaging: alert fan-out to mobile devices

## Fallbacks
- Bhashini rate-limited → AI4Bharat IndicTrans2 + IndicConformer (self-hosted)
- FCM is the only push channel (no fallback needed)

## Rules
- Bhashini is REST-based, use httpx async client
- FCM uses firebase-admin SDK
