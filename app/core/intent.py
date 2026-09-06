"""
Intent Classifier — Fast, cheap intent extraction.

Uses a small model (Haiku-class or Llama-3.1-8B) to classify user
queries into structured intents:
  - current_weather, forecast, alerts, climatology, advisory
  - chit_chat, definition, greeting, unclear

Also extracts: location mention, time range, language, crop (if advisory).
Target: ~100ms latency.
"""
