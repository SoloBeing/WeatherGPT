"""
Chat Route — Primary conversational endpoint.

Accepts text (or transcribed voice) → intent classifier → tool dispatch → phrased response.
This is the main request path from the spec:
  Voice/text → Bhashini ASR → intent classifier → tool layer → big model phrasing → Bhashini TTS
"""
