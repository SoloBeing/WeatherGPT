# data_sources — Context

## Role
Adapters for each weather data provider. Every source normalises to ForecastPoint.

## ForecastPoint Contract
Every source must produce:
- `source: str` — e.g. "open-meteo", "imd", "gfs-0.25"
- `issued_at: datetime` — when the source produced this data
- `valid_at: datetime` — what time the forecast is for
- `lat, lon: float`
- `variables: dict` — temp_c, humidity_pct, wind_speed_mps, etc.

## Sources
| File | Source | Priority |
|------|--------|----------|
| openmeteo.py | Open-Meteo | Always-on fallback (no key, free) |
| imd.py | IMD Mausam | Official Indian data (undocumented API, verify!) |
| gfs.py | GFS Zarr | Reads from ingested Zarr store (not external) |
| ecmwf.py | ECMWF Open Data | IFS 0.25° |
| era5.py | ERA5/CDS | Historical reanalysis only |

## Rules
- Swapping sources must be a config change, not a code change
- Always cite provenance: "per IMD, issued 08:30 IST"
- Open-Meteo is the fallback behind every interface
