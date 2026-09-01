"""
WeatherGPT — Application Configuration

Centralised settings via pydantic-settings. Reads from environment
variables and .env file. Every external service URL, API key, and
tunable lives here — never scattered across modules.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- API ---
    APP_NAME: str = "WeatherGPT"
    DEBUG: bool = False

    # --- Database (PostGIS + TimescaleDB) ---
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/weathergpt"

    # --- Redis Cache ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Object Store (MinIO / S3) ---
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "weathergpt"

    # --- LLM ---
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_API_KEY: str = ""
    INTENT_MODEL: str = "gpt-4o-mini"

    # --- Bhashini (Voice + Translation) ---
    BHASHINI_API_KEY: str = ""
    BHASHINI_USER_ID: str = ""

    # --- Firebase Cloud Messaging ---
    FCM_CREDENTIALS_PATH: str = ""

    # --- Open-Meteo (no key needed) ---
    OPENMETEO_BASE_URL: str = "https://api.open-meteo.com/v1"

    # --- IMD ---
    IMD_BASE_URL: str = "https://mausam.imd.gov.in/api"

    # --- SACHET (NDMA CAP Alerts) ---
    SACHET_FEED_URL: str = "https://sachet.ndma.gov.in/cap_feed"


settings = Settings()
