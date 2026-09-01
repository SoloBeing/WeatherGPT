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

from abc import ABC, abstractmethod

from app.schemas_and_models.schemas import ForecastPoint


class BaseDataSource(ABC):
    """Abstract base class for all weather data sources.

    Every concrete data source must:
    1. Set `source_name` to a unique identifier
    2. Implement `fetch_current()` returning a ForecastPoint
    3. Implement `close()` for resource cleanup
    """

    source_name: str = "unknown"

    @abstractmethod
    async def fetch_current(self, lat: float, lon: float) -> ForecastPoint:
        """Fetch current weather conditions for a geographic point.

        Args:
            lat: Latitude (WGS84)
            lon: Longitude (WGS84)

        Returns:
            ForecastPoint with current conditions populated.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources (e.g. close httpx client)."""
        ...
