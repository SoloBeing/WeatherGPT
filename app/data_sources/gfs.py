"""
GFS Reader — NOAA Global Forecast System via Zarr store.

Raw 0.25° GRIB2, 4 cycles/day (00/06/12/18Z), 384h horizon.
Source: s3://noaa-gfs-bdp-pds (anonymous access).
Ingestion pipeline writes to local Zarr (MinIO), this reads from it.
Normalises to the canonical ForecastPoint and ForecastTimeline schemas.
"""

from datetime import date as dt_date, datetime, timezone
import logging
from typing import Optional

import numpy as np
import pandas as pd
import xarray as xr

from app.database import zarr_storage
from app.data_sources.base import BaseDataSource
from app.models.schemas import (
    DailyForecast,
    ForecastPoint,
    ForecastTimeline,
    HourlyForecast,
)

logger = logging.getLogger(__name__)

# Bounding box bounds
INDIA_LAT_MAX = 38.0
INDIA_LAT_MIN = 6.0
INDIA_LON_MIN = 68.0
INDIA_LON_MAX = 98.0


def _derive_weather_condition(precip_mmh: float, cloud_pct: float) -> tuple[int, str]:
    """Derive WMO weather code and text description from precipitation and cloud cover."""
    if precip_mmh >= 10.0:
        return 65, "Heavy rain"
    elif precip_mmh >= 2.5:
        return 63, "Moderate rain"
    elif precip_mmh >= 0.2:
        return 61, "Light rain"
    elif cloud_pct >= 75.0:
        return 3, "Overcast"
    elif cloud_pct >= 25.0:
        return 2, "Partly cloudy"
    else:
        return 0, "Clear sky"


class GFSClient(BaseDataSource):
    """
    Data source client querying NOAA GFS 0.25° NWP model from Zarr storage.
    """

    source_name: str = "noaa-gfs-0.25"

    def has_data_for(self, lat: float, lon: float) -> bool:
        """
        Check whether this coordinates point falls within India NWP domain
        and at least one valid Zarr cycle is available.
        """
        if not (INDIA_LAT_MIN <= lat <= INDIA_LAT_MAX and INDIA_LON_MIN <= lon <= INDIA_LON_MAX):
            return False
        cycles = zarr_storage.list_saved_cycles(validate=True)
        return len(cycles) > 0

    def _get_active_dataset(self) -> tuple[xr.Dataset, str]:
        """Open the most recent available valid GFS Zarr store, falling back to older cycles if needed."""
        cycles = zarr_storage.list_saved_cycles(validate=True)
        if not cycles:
            raise FileNotFoundError("No GFS Zarr cycle datasets found in storage.")

        last_error: Exception | None = None
        for cycle_key in cycles:
            store_path = f"data/zarr_stores/gfs/{cycle_key}.zarr"
            try:
                ds = zarr_storage.open_dataset(store_path)
                return ds, cycle_key
            except Exception as exc:
                logger.warning(
                    "Failed to open GFS Zarr cycle '%s' (%s). Trying next available cycle...",
                    cycle_key,
                    exc,
                )
                last_error = exc
                continue

        raise FileNotFoundError(
            f"All {len(cycles)} candidate GFS Zarr cycles failed to open. Last error: {last_error}"
        )

    async def fetch_current(self, lat: float, lon: float) -> ForecastPoint:
        """
        Extract nearest-neighbor current/initial conditions from the latest GFS Zarr cycle.
        """
        ds, cycle_key = self._get_active_dataset()
        try:
            # Nearest neighbor interpolation
            pt = ds.sel(latitude=lat, longitude=lon, method="nearest")

            # Step index 0 represents initial analysis / closest lead time
            step_idx = 0

            temp_c = float(pt["temperature_c"].values[step_idx]) if "temperature_c" in pt else None
            rh_pct = float(pt["r2"].values[step_idx]) if "r2" in pt else None
            w_spd_ms = float(pt["wind_speed"].values[step_idx]) if "wind_speed" in pt else None
            w_spd_kmh = round(w_spd_ms * 3.6, 1) if w_spd_ms is not None else None
            w_dir_deg = float(pt["wind_direction"].values[step_idx]) if "wind_direction" in pt else None
            press_hpa = float(pt["pressure_hpa"].values[step_idx]) if "pressure_hpa" in pt else None
            precip_mm = float(pt["precip_rate_mmh"].values[step_idx]) if "precip_rate_mmh" in pt else 0.0
            cloud_pct = float(pt["tcc"].values[step_idx]) if "tcc" in pt else 0.0

            wmo_code, weather_desc = _derive_weather_condition(precip_mm, cloud_pct)

            # Issued / Valid timestamps
            now = datetime.now(timezone.utc)
            valid_at = now
            if "valid_time" in pt:
                try:
                    vt_raw = pt["valid_time"].values[step_idx]
                    valid_at = pd.to_datetime(vt_raw).to_pydatetime().replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            issued_at = now
            if "time" in ds.coords:
                try:
                    issued_at = pd.to_datetime(ds.coords["time"].values).to_pydatetime().replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            return ForecastPoint(
                source=f"NOAA GFS (0.25° NWP via Zarr - {cycle_key})",
                issued_at=issued_at,
                valid_at=valid_at,
                lat=round(lat, 4),
                lon=round(lon, 4),
                temperature_c=round(temp_c, 1) if temp_c is not None else None,
                humidity_pct=round(rh_pct, 1) if rh_pct is not None else None,
                wind_speed_kmh=w_spd_kmh,
                wind_direction_deg=round(w_dir_deg, 1) if w_dir_deg is not None else None,
                pressure_hpa=round(press_hpa, 1) if press_hpa is not None else None,
                precipitation_mm=round(precip_mm, 2),
                cloud_cover_pct=round(cloud_pct, 1),
                weather_code=wmo_code,
                weather_description=weather_desc,
            )
        finally:
            ds.close()

    async def fetch_forecast(
        self,
        lat: float,
        lon: float,
        days: int = 5,
        include_hourly: bool = False,
    ) -> ForecastTimeline:
        """
        Extract multi-day / lead-step forecast from GFS Zarr store.
        """
        ds, cycle_key = self._get_active_dataset()
        try:
            pt = ds.sel(latitude=lat, longitude=lon, method="nearest")

            num_steps = pt.sizes.get("step", 1)
            now = datetime.now(timezone.utc)

            issued_at = now
            if "time" in ds.coords:
                try:
                    issued_at = pd.to_datetime(ds.coords["time"].values).to_pydatetime().replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            # Aggregate slices by date
            daily_buckets: dict[dt_date, list[dict[str, float]]] = {}
            hourly_slices: list[HourlyForecast] = []

            for i in range(num_steps):
                try:
                    step_valid = pd.to_datetime(pt["valid_time"].values[i]).to_pydatetime().replace(tzinfo=timezone.utc)
                except Exception:
                    step_valid = now

                target_date = step_valid.date()
                t_c = float(pt["temperature_c"].values[i]) if "temperature_c" in pt else 25.0
                rh = float(pt["r2"].values[i]) if "r2" in pt else 60.0
                w_ms = float(pt["wind_speed"].values[i]) if "wind_speed" in pt else 5.0
                w_kmh = w_ms * 3.6
                p_mm = float(pt["precip_rate_mmh"].values[i]) if "precip_rate_mmh" in pt else 0.0
                c_pct = float(pt["tcc"].values[i]) if "tcc" in pt else 30.0

                code, desc = _derive_weather_condition(p_mm, c_pct)

                if target_date not in daily_buckets:
                    daily_buckets[target_date] = []

                daily_buckets[target_date].append({
                    "temp": t_c,
                    "humidity": rh,
                    "wind": w_kmh,
                    "precip": p_mm,
                    "cloud": c_pct,
                    "code": code,
                    "desc": desc,
                })

                if include_hourly:
                    hourly_slices.append(
                        HourlyForecast(
                            valid_at=step_valid,
                            temperature_c=round(t_c, 1),
                            humidity_pct=round(rh, 1),
                            precipitation_mm=round(p_mm, 2),
                            wind_speed_kmh=round(w_kmh, 1),
                            weather_code=code,
                            weather_description=desc,
                        )
                    )

            # Build DailyForecast list
            daily_forecasts: list[DailyForecast] = []
            for d, items in list(daily_buckets.items())[:days]:
                temps = [x["temp"] for x in items]
                winds = [x["wind"] for x in items]
                precips = [x["precip"] for x in items]
                dom_code = items[0]["code"]
                dom_desc = items[0]["desc"]

                daily_forecasts.append(
                    DailyForecast(
                        date=d,
                        temp_max_c=round(max(temps), 1),
                        temp_min_c=round(min(temps), 1),
                        precipitation_sum_mm=round(sum(precips), 2),
                        wind_speed_max_kmh=round(max(winds), 1),
                        weather_code=dom_code,
                        weather_description=dom_desc,
                    )
                )

            return ForecastTimeline(
                source=f"NOAA GFS (0.25° NWP via Zarr - {cycle_key})",
                issued_at=issued_at,
                lat=round(lat, 4),
                lon=round(lon, 4),
                daily=daily_forecasts,
                hourly=hourly_slices if include_hourly else None,
            )
        finally:
            ds.close()

    async def close(self) -> None:
        """Clean up resources if any."""
        pass


# Shared singleton instance
gfs_client = GFSClient()

