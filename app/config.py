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
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: float = 30.0
    DB_POOL_RECYCLE: int = 1800

    # --- Redis Cache ---
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_SOCKET_TIMEOUT: float = 2.0
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 2.0

    # --- HTTP Client Connection Pools ---
    HTTP_MAX_CONNECTIONS: int = 100
    HTTP_MAX_KEEPALIVE_CONNECTIONS: int = 20
    HTTP_KEEPALIVE_EXPIRY: float = 30.0
    HTTP_TIMEOUT: float = 10.0

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
    BHASHINI_INFERENCE_KEY: str = ""
    BHASHINI_ULCA_CONFIG_URL: str = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"
    BHASHINI_PIPELINE_ID: str = "64392f96daac500b55c543cd"
    BHASHINI_TTS_GENDER: str = "female"

    # --- Fallback ASR (Groq Whisper) ---
    GROQ_WHISPER_MODEL: str = "whisper-large-v3"

    # --- Firebase Cloud Messaging ---
    FCM_CREDENTIALS_PATH: str = ""

    # --- Open-Meteo (no key needed) ---
    OPENMETEO_BASE_URL: str = "https://api.open-meteo.com/v1"

    # --- IMD ---
    IMD_BASE_URL: str = "https://mausam.imd.gov.in/api"

    # --- SACHET (NDMA Alerts) ---
    SACHET_FEED_URL: str = "https://sachet.ndma.gov.in/cap_public_website/FetchAllAlertDetails"
    SACHET_NOWCAST_URL: str = "https://sachet.ndma.gov.in/cap_public_website/FetchIMDNowcastAlerts"


settings = Settings()
