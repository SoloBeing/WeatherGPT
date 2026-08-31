"""
LLM Router — The orchestrator that ties intent → tools → response.

Key principle from the spec:
  "The LLM never computes or recalls weather. It only (a) parses the
   query into a structured intent, (b) calls tools, (c) phrases the
   tool output in the user's language. Every number comes from a
   deterministic service."

Flow:
  1. Small/fast model classifies intent (~100ms)
  2. If needs numbers → tool call(s)
  3. If chit-chat/definition → RAG over IMD docs
  4. Big model phrases the structured JSON into prose (temp 0.2)
"""
