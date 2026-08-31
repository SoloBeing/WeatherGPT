"""
Base Tool Interface — Common contract for all weather tools.

Every tool returns structured JSON. The tool layer enforces a single
internal schema — every source normalises to ForecastPoint with a
'source' and 'issued_at' field. Swapping sources is a config change.
"""
