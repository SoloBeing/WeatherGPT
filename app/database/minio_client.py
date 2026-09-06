"""
MinIO / S3 Object Store & Zarr Storage Layer.

Manages numerical weather prediction (GFS / ECMWF) Zarr datasets.
Seamlessly falls back to local disk storage (`data/zarr_stores/`) when
MinIO is unreachable in standalone development environments.
"""

from io import BytesIO
import logging
import os
from pathlib import Path
from typing import Any
import urllib3

from minio import Minio
from minio.error import S3Error
import xarray as xr

from app.config import settings

logger = logging.getLogger(__name__)

LOCAL_ZARR_BASE = Path("data/zarr_stores")


class CorruptedZarrStoreError(Exception):
    """Raised when a Zarr store directory is empty, corrupted, or missing metadata."""
    pass


def is_valid_zarr_store(path: Path | str) -> bool:
    """Validate whether a given directory path is a well-formed, non-empty Zarr store.

    Checks:
    1. Path exists and is a directory.
    2. Directory is non-empty.
    3. Contains standard Zarr markers (zarr.json for v3, or .zgroup/.zmetadata/.zattrs for v2,
       or variable subdirectories containing array metadata).
    """
    p = Path(path)
    if not p.exists() or not p.is_dir():
        return False

    try:
        entries = list(p.iterdir())
    except OSError:
        return False

    if not entries:
        return False

    # Check for direct root metadata markers (Zarr v3 / v2)
    valid_root_markers = {"zarr.json", ".zgroup", ".zmetadata", ".zattrs"}
    entry_names = {e.name for e in entries}
    if entry_names & valid_root_markers:
        return True

    # Check if any child subdirectory contains array metadata
    for e in entries:
        if e.is_dir():
            try:
                sub_names = {sub.name for sub in e.iterdir()}
                if sub_names & {"zarr.json", ".zarray", ".zattrs"}:
                    return True
            except OSError:
                continue

    return False


class MinioZarrStorage:
    """
    Object storage client for Zarr grids, supporting MinIO / S3
    and local filesystem fallback.
    """

    def __init__(
        self,
        endpoint: str = settings.MINIO_ENDPOINT,
        access_key: str = settings.MINIO_ACCESS_KEY,
        secret_key: str = settings.MINIO_SECRET_KEY,
        bucket: str = settings.MINIO_BUCKET,
        secure: bool = False,
    ):
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.secure = secure
        self._minio_client: Minio | None = None
        self._is_minio_available: bool | None = None

    def get_client(self) -> Minio:
        """Get or initialize the underlying Minio client with short connect timeout."""
        if self._minio_client is None:
            http_client = urllib3.PoolManager(
                timeout=urllib3.Timeout(connect=1.5, read=3.0),
                retries=urllib3.Retry(total=1, backoff_factor=0.2),
            )
            self._minio_client = Minio(
                endpoint=self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
                http_client=http_client,
            )
        return self._minio_client

    def is_available(self) -> bool:
        """Check whether MinIO endpoint is reachable and responsive."""
        if self._is_minio_available is not None:
            return self._is_minio_available
        try:
            client = self.get_client()
            client.bucket_exists(self.bucket)
            self._is_minio_available = True
            logger.info("MinIO object store is online and accessible.")
        except Exception as exc:
            self._is_minio_available = False
            logger.info(
                f"MinIO not reachable ({exc.__class__.__name__}). "
                "Using local filesystem Zarr store fallback."
            )
        return self._is_minio_available

    def ensure_bucket(self) -> bool:
        """Ensure the target bucket exists on MinIO."""
        if not self.is_available():
            return False
        try:
            client = self.get_client()
            if not client.bucket_exists(self.bucket):
                client.make_bucket(self.bucket)
                logger.info(f"Created MinIO bucket: {self.bucket}")
            return True
        except Exception as exc:
            logger.warning(f"Failed to ensure bucket {self.bucket}: {exc}")
            return False

    def save_dataset(
        self,
        ds: xr.Dataset,
        cycle_key: str,
        subfolder: str = "gfs",
    ) -> str:
        """
        Save an xarray Dataset to a chunked Zarr store.

        If MinIO is available, saves or syncs to MinIO.
        Otherwise, writes to `data/zarr_stores/{subfolder}/{cycle_key}.zarr`.

        Returns:
            The storage path or URI where the dataset was persisted.
        """
        # Optimal chunking for spatial point queries: chunk along time, keep lat/lon compact
        chunk_dims: dict[str, int] = {}
        for dim in ds.dims:
            if dim == "time" or dim == "step":
                chunk_dims[str(dim)] = min(4, ds.sizes[dim])
            elif dim in ("latitude", "lat"):
                chunk_dims[str(dim)] = min(32, ds.sizes[dim])
            elif dim in ("longitude", "lon"):
                chunk_dims[str(dim)] = min(32, ds.sizes[dim])

        if chunk_dims:
            try:
                ds = ds.chunk(chunk_dims)
            except Exception as e:
                logger.debug(f"Could not re-chunk dataset: {e}")

        # Determine target path
        target_dir = LOCAL_ZARR_BASE / subfolder
        target_dir.mkdir(parents=True, exist_ok=True)
        store_path = target_dir / f"{cycle_key}.zarr"

        # Write to local Zarr store
        ds.to_zarr(store_path, mode="w", consolidated=False)
        logger.info(f"Successfully saved Zarr store at: {store_path}")

        # If MinIO is reachable, sync objects to MinIO bucket
        if self.is_available() and self.ensure_bucket():
            try:
                client = self.get_client()
                for root, _, files in os.walk(store_path):
                    for file in files:
                        local_file = os.path.join(root, file)
                        rel_path = os.path.relpath(local_file, LOCAL_ZARR_BASE)
                        object_name = rel_path.replace(os.path.sep, "/")
                        client.fput_object(self.bucket, object_name, local_file)
                logger.info(f"Mirrored Zarr dataset to s3://{self.bucket}/{subfolder}/{cycle_key}.zarr")
                return f"s3://{self.bucket}/{subfolder}/{cycle_key}.zarr"
            except Exception as exc:
                logger.warning(f"Failed to mirror Zarr to MinIO: {exc}. Retaining local store.")

        return str(store_path)

    def open_dataset(self, store_path: str) -> xr.Dataset:
        """
        Open a Zarr store given its file path or s3 URI with corruption guardrails.

        Supports local paths as well as local fallbacks if an s3 URI is passed
        but MinIO is offline.
        """
        local_path: Path | None = None

        if store_path.startswith("s3://"):
            parts = store_path.replace("s3://", "").split("/", 1)
            if len(parts) == 2:
                _, rel_path = parts
                local_fallback = LOCAL_ZARR_BASE / rel_path
                if local_fallback.exists():
                    local_path = local_fallback

            if local_path is None and self.is_available():
                s3_endpoint = f"http://{self.endpoint}" if not self.secure else f"https://{self.endpoint}"
                storage_options = {
                    "key": self.access_key,
                    "secret": self.secret_key,
                    "client_kwargs": {"endpoint_url": s3_endpoint},
                }
                try:
                    return xr.open_zarr(store_path, storage_options=storage_options, consolidated=False)
                except Exception as exc:
                    raise CorruptedZarrStoreError(
                        f"Failed to open remote Zarr store '{store_path}': {exc}"
                    ) from exc
        else:
            local_path = Path(store_path)

        if local_path is not None:
            if not local_path.exists():
                raise FileNotFoundError(f"Zarr store directory does not exist: {local_path}")
            if not is_valid_zarr_store(local_path):
                raise CorruptedZarrStoreError(
                    f"Zarr store at '{local_path}' is corrupted, incomplete, or missing metadata."
                )
            try:
                return xr.open_zarr(local_path, consolidated=False)
            except Exception as exc:
                raise CorruptedZarrStoreError(
                    f"Failed to decode Zarr store at '{local_path}': {exc}"
                ) from exc

        raise FileNotFoundError(f"Zarr store not found or inaccessible: {store_path}")

    def list_saved_cycles(self, subfolder: str = "gfs", validate: bool = True) -> list[str]:
        """List all available stored cycle keys, optionally filtering corrupted stores."""
        folder = LOCAL_ZARR_BASE / subfolder
        if not folder.exists():
            return []

        cycles: list[str] = []
        for d in folder.iterdir():
            if d.is_dir() and d.name.endswith(".zarr"):
                if validate and not is_valid_zarr_store(d):
                    logger.warning("Ignoring corrupted or incomplete Zarr directory: %s", d)
                    continue
                cycles.append(d.name.removesuffix(".zarr"))

        return sorted(cycles, reverse=True)


# Singleton instance
zarr_storage = MinioZarrStorage()
