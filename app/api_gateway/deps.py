"""
API Dependencies — FastAPI dependency injection.

Provides shared resources to route handlers:
  - get_db_session()  → async SQLAlchemy session
  - get_redis()       → Redis client
  - get_settings()    → app config
"""

from app.config import Settings, settings


def get_settings() -> Settings:
    """Return the global settings singleton.

    Usage in routes:
        @router.get("/...")
        async def my_route(cfg: Settings = Depends(get_settings)):
            ...
    """
    return settings
