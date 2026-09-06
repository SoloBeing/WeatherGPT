"""
Scheduler Setup — APScheduler configuration for background ingestion jobs.

Schedules:
  - GFS Ingest: 4x daily at 03:30, 09:30, 15:30, 21:30 UTC (~3.5h after 00Z, 06Z, 12Z, 18Z cycles)
  - SACHET Poll: Every 60 seconds (NDMA CAP alerts)
  - Forecast Precompute: Top Indian cities/towns cached in Redis after each GFS cycle
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any

import numpy as np
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database import cache, zarr_storage
from app.pipelines.gfs_pipeline import gfs_pipeline
from app.pipelines.sachet_poller import sachet_poller

logger = logging.getLogger(__name__)

# Key Indian metropolitan hubs and state capitals for instant warm-cache responses
KEY_INDIAN_TOWNS = [
    {"name": "Delhi", "lat": 28.6139, "lon": 77.2090},
    {"name": "Mumbai", "lat": 19.0760, "lon": 72.8777},
    {"name": "Bengaluru", "lat": 12.9716, "lon": 77.5946},
    {"name": "Chennai", "lat": 13.0827, "lon": 80.2707},
    {"name": "Kolkata", "lat": 22.5726, "lon": 88.3639},
    {"name": "Hyderabad", "lat": 17.3850, "lon": 78.4867},
    {"name": "Ahmedabad", "lat": 23.0225, "lon": 72.5714},
    {"name": "Pune", "lat": 18.5204, "lon": 73.8567},
    {"name": "Jaipur", "lat": 26.9124, "lon": 75.7873},
    {"name": "Lucknow", "lat": 26.8467, "lon": 80.9462},
    {"name": "Patna", "lat": 25.5941, "lon": 85.1376},
    {"name": "Bhopal", "lat": 23.2599, "lon": 77.4126},
    {"name": "Chandigarh", "lat": 30.7333, "lon": 76.7794},
    {"name": "Bhubaneswar", "lat": 20.2961, "lon": 85.8245},
    {"name": "Guwahati", "lat": 26.1445, "lon": 91.7362},
    {"name": "Thiruvananthapuram", "lat": 8.5241, "lon": 76.9366},
    {"name": "Shimla", "lat": 31.1048, "lon": 77.1734},
    {"name": "Srinagar", "lat": 34.0837, "lon": 74.7973},
]


async def precompute_top_towns(zarr_path: str | None = None) -> int:
    """
    Extract point forecasts from Zarr store for key Indian towns and pre-warm Redis.
    Allows point forecast queries to return in <10ms without hitting disk.
    """
    cycles = zarr_storage.list_saved_cycles()
    if not cycles and not zarr_path:
        logger.info("No saved Zarr cycles available for precomputation.")
        return 0

    target_path = zarr_path or f"data/zarr_stores/gfs/{cycles[0]}.zarr"
    logger.info(f"Precomputing town forecasts from Zarr store: {target_path}")

    try:
        ds = zarr_storage.open_dataset(target_path)
    except Exception as exc:
        logger.warning(f"Could not open Zarr store for precomputation: {exc}")
        return 0

    try:
        warmed_batch: list[tuple[float, float, int, str, int]] = []

        lat_name = "latitude" if "latitude" in ds.coords else ("lat" if "lat" in ds.coords else None)
        lon_name = "longitude" if "longitude" in ds.coords else ("lon" if "lon" in ds.coords else None)
        lats = np.asarray(ds.coords[lat_name].values) if lat_name else None
        lons = np.asarray(ds.coords[lon_name].values) if lon_name else None

        for town in KEY_INDIAN_TOWNS:
            try:
                lat = town["lat"]
                lon = town["lon"]

                # Fast 1D nearest index slicing
                if lats is not None and lons is not None and lat_name and lon_name:
                    lat_idx = int(np.abs(lats - lat).argmin())
                    lon_idx = int(np.abs(lons - lon).argmin())
                    point = ds.isel({lat_name: lat_idx, lon_name: lon_idx})
                else:
                    point = ds.sel(latitude=lat, longitude=lon, method="nearest")

                lead_steps = []
                num_steps = point.sizes.get("step", 1)
                for i in range(num_steps):
                    temp_c = float(point["temperature_c"].values[i]) if "temperature_c" in point else 25.0
                    rh = float(point["r2"].values[i]) if "r2" in point else 60.0
                    w_spd = float(point["wind_speed"].values[i]) if "wind_speed" in point else 5.0
                    w_dir = float(point["wind_direction"].values[i]) if "wind_direction" in point else 0.0
                    press = float(point["pressure_hpa"].values[i]) if "pressure_hpa" in point else 1010.0
                    precip = float(point["precip_rate_mmh"].values[i]) if "precip_rate_mmh" in point else 0.0

                    lead_steps.append({
                        "step_index": i,
                        "temperature_c": round(temp_c, 1),
                        "humidity_percent": round(rh, 1),
                        "wind_speed_ms": round(w_spd, 1),
                        "wind_direction_deg": round(w_dir, 1),
                        "pressure_hpa": round(press, 1),
                        "precipitation_mmh": round(precip, 2),
                    })

                forecast_payload = {
                    "source": "NOAA GFS (0.25° NWP via Zarr)",
                    "location": town["name"],
                    "latitude": lat,
                    "longitude": lon,
                    "cached_at": datetime.now(timezone.utc).isoformat(),
                    "forecasts": lead_steps,
                }

                warmed_batch.append((lat, lon, 3, json.dumps(forecast_payload), 21600))
            except Exception as exc:
                logger.debug(f"Failed precomputing town {town['name']}: {exc}")

        if warmed_batch:
            # Atomic pipelined write of all town forecasts to Redis
            await cache.set_forecasts_batch(warmed_batch)

        logger.info(f"Successfully warmed cache for {len(warmed_batch)}/{len(KEY_INDIAN_TOWNS)} key towns.")
        return len(warmed_batch)
    finally:
        ds.close()


async def job_gfs_ingestion() -> None:
    """Scheduled task to execute GFS cycle fetch, Zarr storage, and town warming."""
    logger.info("Triggering scheduled GFS NWP ingestion job...")
    try:
        zarr_path, _ = await gfs_pipeline.run_pipeline(force_synthetic=False, use_db=True)
        logger.info(f"Scheduled GFS ingest finished. Store: {zarr_path}")
        # Warm top towns
        await precompute_top_towns(zarr_path)
    except Exception as exc:
        logger.error(f"Scheduled GFS ingest encountered error: {exc}", exc_info=True)


async def job_sachet_poll() -> None:
    """Scheduled task to poll NDMA SACHET CAP feeds for new disaster alerts."""
    try:
        await sachet_poller.poll_once()
    except Exception as exc:
        logger.warning(f"Error during scheduled SACHET alert poll: {exc}")


class IngestionScheduler:
    """
    Central scheduler for background ingestion jobs.
    """

    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler()
        self._is_running = False

    def setup_jobs(self) -> None:
        """Configure job schedules."""
        # 1. GFS NWP Cycle Ingestion: 4x daily, ~3.5h after 00, 06, 12, 18 UTC
        self.scheduler.add_job(
            job_gfs_ingestion,
            trigger=CronTrigger(hour="3,9,15,21", minute="30", timezone="UTC"),
            id="gfs_nwp_ingest",
            name="NOAA GFS 0.25° Ingestion",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # 2. SACHET Alert Polling: every 60 seconds
        self.scheduler.add_job(
            job_sachet_poll,
            trigger=IntervalTrigger(seconds=60),
            id="sachet_alert_poll",
            name="NDMA SACHET CAP Feed Poller",
            replace_existing=True,
            misfire_grace_time=30,
        )

        logger.info("Configured APScheduler jobs: GFS (4x/day at 03:30, 09:30, 15:30, 21:30 UTC), SACHET (60s)")

    def start(self) -> None:
        """Start the async scheduler."""
        if not self._is_running:
            self.setup_jobs()
            self.scheduler.start()
            self._is_running = True
            logger.info("APScheduler started successfully.")

    def shutdown(self) -> None:
        """Shut down the scheduler cleanly."""
        if self._is_running:
            self.scheduler.shutdown(wait=False)
            self._is_running = False
            logger.info("APScheduler shut down.")

    async def trigger_gfs_now(self, force_synthetic: bool = False) -> str:
        """Manually trigger immediate GFS ingestion and cache warming."""
        logger.info("Manual immediate GFS ingestion triggered.")
        zarr_path, _ = await gfs_pipeline.run_pipeline(force_synthetic=force_synthetic, use_db=True)
        await precompute_top_towns(zarr_path)
        return zarr_path


# Shared singleton scheduler
ingestion_scheduler = IngestionScheduler()
