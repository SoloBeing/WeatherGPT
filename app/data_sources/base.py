"""
Base Data Source — Common interface + ForecastPoint schema.

Every data source (Open-Meteo, IMD, GFS, ECMWF, ERA5, WRF) normalises
its output to the same ForecastPoint object. This is the single internal
schema that the tool layer depends on.

ForecastPoint includes:
  - source: str          (e.g. "open-meteo", "imd", "gfs-0.25")
  - issued_at: datetime  (when the source produced this data)
  - valid_at: datetime   (what time the forecast is for)
  - lat, lon: float
  - variables: dict      (temp_c, humidity_pct, wind_speed_mps, etc.)

"Then swapping sources is a config change, and you can cite provenance
 in the answer ('per IMD, issued 08:30 IST'), which reads as rigour."
"""
