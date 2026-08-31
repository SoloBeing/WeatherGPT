"""
Location Resolver — Disambiguate Indian place names.

From the spec:
  "Indian place names are ambiguous and voice input mangles them.
   Build a gazetteer table (village/town/district, ~600k rows from
   LGD or GeoNames) with pg_trgm fuzzy matching, and resolve BEFORE
   the LLM sees the query."

Ask a disambiguating question when confidence is low.
"""
