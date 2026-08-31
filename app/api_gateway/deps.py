"""
API Dependencies — FastAPI dependency injection.

Provides shared resources to route handlers:
  - get_db_session()  → async SQLAlchemy session
  - get_redis()       → Redis client
  - get_settings()    → app config
"""
