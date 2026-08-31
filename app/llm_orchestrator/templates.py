"""
Multilingual Response Templates — Factual core in verified templates.

From the spec:
  "Don't translate free-form LLM prose — errors compound and you can't
   audit them. Instead: tools return structured values → fill a template
   per language for the factual core → use the LLM only for surrounding
   conversational glue."

Example:
  "{district} में कल {rain_mm} मिमी बारिश की संभावना है"

Templates are verifiable, instant, and never invent a number.
"""
