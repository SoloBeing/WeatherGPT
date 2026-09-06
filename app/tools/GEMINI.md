# tools — Context

## Role
The 5 spec-defined tools + location resolver. Each tool returns structured JSON.

## Tools
| Tool | Signature | Returns |
|------|-----------|---------|
| get_current | (lat, lon) | Current conditions |
| get_forecast | (lat, lon, hours) | Hourly/daily forecast |
| get_alerts | (geom) | Active weather alerts |
| get_climatology | (lat, lon, var, years) | Historical climate data |
| get_advisory | (crop, stage, forecast) | Agricultural advisory |

## Location Resolver
- Gazetteer table (~600k rows from LGD/GeoNames)
- pg_trgm fuzzy matching in PostGIS
- Resolves BEFORE the LLM sees the query
- Ask disambiguating question when confidence is low

## Rules
- Every tool checks Redis first (TTL 1h), then Zarr/Postgres, then external API
- All tools return the same structured JSON schema
- Tools never call the LLM — they are deterministic
