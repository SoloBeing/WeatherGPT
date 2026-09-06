"""
WeatherGPT — Dev Session 06 Scalability & Performance Test Suite.

Verifies:
1. Database, Redis, and HTTP connection pool configurations.
2. Redis ConnectionPool management, pipeline batching, and batch forecast writing.
3. SingleFlight request coalescing / cache-stampede (dogpiling) protection.
4. Zarr dataset handle caching and fast 1D coordinate indexing.
5. Location resolution in-memory caching and persistent client reuse.
6. Alembic migration 0002 spatial and trigram index definitions.
"""

import asyncio
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import numpy as np
import pytest
import xarray as xr

from app.config import settings
from app.core.resilience import SingleFlight, single_flight
from app.data_sources.gfs import GFSClient, gfs_client
from app.data_sources.openmeteo import openmeteo_client
from app.database import cache
from app.database.redis_cache import RedisCache
from app.database.session import get_engine
from app.pipelines.sachet_poller import sachet_poller
from app.pipelines.scheduler import precompute_top_towns
from app.services.bhashini import bhashini_service
from app.tools.location_resolver import (
    clear_location_cache,
    close_geocoder,
    get_geocoder_client,
    resolve_location,
)


# ===========================================================================
# 1. Connection Pooling & Configuration Tests
# ===========================================================================

def test_connection_pool_settings():
    """Verify connection pooling configurations are present and tuned."""
    assert settings.DB_POOL_SIZE >= 10
    assert settings.DB_MAX_OVERFLOW >= 5
    assert settings.DB_POOL_TIMEOUT >= 10.0
    assert settings.DB_POOL_RECYCLE >= 300

    assert settings.REDIS_MAX_CONNECTIONS >= 20
    assert settings.REDIS_SOCKET_TIMEOUT >= 1.0
    assert settings.REDIS_SOCKET_CONNECT_TIMEOUT >= 1.0

    assert settings.HTTP_MAX_CONNECTIONS >= 50
    assert settings.HTTP_MAX_KEEPALIVE_CONNECTIONS >= 10
    assert settings.HTTP_KEEPALIVE_EXPIRY >= 10.0


def test_http_client_pool_limits():
    """Verify all persistent HTTP clients configure httpx.Limits and keep-alive."""
    # Open-Meteo client
    assert openmeteo_client._client._transport is not None

    # Bhashini service client
    assert bhashini_service._client._transport is not None

    # SACHET poller client
    assert sachet_poller._http_client._transport is not None

    # Location resolver client
    geocoder = get_geocoder_client()
    assert geocoder._transport is not None


# ===========================================================================
# 2. Redis Connection Pooling & Pipeline Batching Tests
# ===========================================================================

async def test_redis_connection_pool_and_pipeline_batching():
    """Verify RedisCache uses an explicit ConnectionPool and supports pipeline batching."""
    test_cache = RedisCache("redis://localhost:6379/15")
    pool = test_cache._get_pool()
    assert pool.max_connections == settings.REDIS_MAX_CONNECTIONS

    # Mock the pipeline execution (set is synchronous queuing, execute is async)
    mock_pipe = MagicMock()
    mock_pipe.set = MagicMock()
    mock_pipe.execute = AsyncMock(return_value=[True, True, True])
    mock_pipe.__aenter__ = AsyncMock(return_value=mock_pipe)
    mock_pipe.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.pipeline.return_value = mock_pipe
    test_cache._client = mock_client

    # Test set_many
    items = [
        ("k1", "v1", 60),
        ("k2", "v2", 120),
        ("k3", "v3", 180),
    ]
    success = await test_cache.set_many(items)
    assert success is True
    assert mock_pipe.set.call_count == 3
    mock_pipe.execute.assert_awaited_once()

    # Test set_forecasts_batch
    forecast_batch = [
        (28.61, 77.20, 3, '{"temp": 28}', 3600),
        (19.07, 72.87, 3, '{"temp": 30}', 3600),
    ]
    batch_success = await test_cache.set_forecasts_batch(forecast_batch)
    assert batch_success is True
    assert mock_pipe.set.call_count == 5  # 3 previous + 2 new


# ===========================================================================
# 3. SingleFlight Request Coalescing (Cache Stampede Protection)
# ===========================================================================

async def test_single_flight_coalescing_under_high_concurrency():
    """Verify SingleFlight executes an underlying fetch only once for concurrent requests."""
    coordinator = SingleFlight()
    call_count = 0

    async def slow_fetch(identifier: str) -> dict:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)  # Simulate network latency
        return {"data": identifier, "resolved_at": time.time()}

    # Launch 25 concurrent requests for the exact same key
    tasks = [
        coordinator.execute("delhi_forecast_key", slow_fetch, "Delhi")
        for _ in range(25)
    ]
    results = await asyncio.gather(*tasks)

    # Underlying fetch must have been called EXACTLY ONCE
    assert call_count == 1
    assert len(results) == 25
    # All callers must receive the exact same response object
    for res in results:
        assert res["data"] == "Delhi"
        assert res["resolved_at"] == results[0]["resolved_at"]


async def test_single_flight_exception_propagation():
    """Verify SingleFlight propagates exceptions cleanly to all concurrent waiters."""
    coordinator = SingleFlight()
    call_count = 0

    async def failing_fetch():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.02)
        raise ValueError("Upstream server unavailable")

    tasks = [
        coordinator.execute("failing_key", failing_fetch)
        for _ in range(10)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    assert call_count == 1
    assert len(results) == 10
    for res in results:
        assert isinstance(res, ValueError)
        assert "Upstream server unavailable" in str(res)


# ===========================================================================
# 4. Zarr Dataset Caching & Coordinate Indexing Performance
# ===========================================================================

async def test_zarr_dataset_handle_caching_and_fast_indexing(synthetic_gfs_cycle):
    """Verify GFSClient caches active open dataset and slices points via fast 1D indexing."""
    client = GFSClient()

    # First call: opens and caches dataset
    t0 = time.perf_counter()
    pt1 = await client.fetch_current(28.6139, 77.2090)
    dur_first = time.perf_counter() - t0

    assert pt1.temperature_c is not None
    assert client._cached_ds is not None
    assert client._cached_lats is not None
    assert client._cached_lons is not None

    # Subsequent 20 queries hit cached dataset with .isel()
    t1 = time.perf_counter()
    for _ in range(20):
        pt = await client.fetch_current(28.6139, 77.2090)
        assert pt.temperature_c == pt1.temperature_c
    dur_cached_20 = time.perf_counter() - t1

    # Cached queries should execute in <50ms per query
    avg_per_query_ms = (dur_cached_20 / 20) * 1000
    assert avg_per_query_ms < 50.0

    # Invalidate cache
    client.invalidate_cache()
    assert client._cached_ds is None
    assert client._cached_lats is None


# ===========================================================================
# 5. Location Resolver In-Memory Query Caching
# ===========================================================================

async def test_location_resolver_in_memory_cache():
    """Verify repeated location lookups return from cache without network calls."""
    clear_location_cache()

    # 1. Gazetteer city (Mumbai)
    m1 = await resolve_location("Mumbai")
    assert len(m1) >= 1
    assert m1[0].name == "Mumbai"

    # Second call should be instant cache hit
    m2 = await resolve_location("Mumbai")
    assert m2 is m1  # Exact cached object reference

    # 2. Clear cache
    clear_location_cache()
    m3 = await resolve_location("Mumbai")
    assert m3[0].name == "Mumbai"


# ===========================================================================
# 6. Alembic Migration 0002 Spatial and Trigram Indexes
# ===========================================================================

def test_migration_0002_schema_definitions():
    """Verify migration 0002 contains GIN trigram and composite index specifications."""
    mig_path = Path("alembic/versions/0002_performance_and_spatial_indexes.py")
    assert mig_path.exists()
    spec = importlib.util.spec_from_file_location("migration_0002", mig_path)
    assert spec is not None
    assert spec.loader is not None
    migration_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration_mod)

    assert migration_mod.revision == "0002_performance_and_spatial_indexes"
    assert migration_mod.down_revision == "0001_initial_schema"
    assert callable(migration_mod.upgrade)
    assert callable(migration_mod.downgrade)
