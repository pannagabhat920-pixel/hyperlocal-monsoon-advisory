from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Union
import json

class Settings(BaseSettings):
    ENV: str = "development"

    # Database
    POSTGRES_USER: str = "pannaga"
    POSTGRES_PASSWORD: str = "pannaga"
    POSTGRES_DB: str = "pannaga"
    POSTGRES_HOST: str = "postgis"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+asyncpg://pannaga:pannaga@postgis:5432/pannaga"
    DATABASE_URL_SYNC: str = "postgresql://pannaga:pannaga@postgis:5432/pannaga"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Authentication & Security
    SECRET_KEY: str = "supersecretkey_for_development_only_please_change_in_production_minimum_32_characters"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    DEV_OTP: str = "000000"
    DEV_OTP_ENABLED: bool = True

    # Messaging Provider: 'console' | 'mock' | 'twilio'
    MESSAGING_PROVIDER: str = "console"
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_PHONE_NUMBER: str = ""
    PUBLIC_BASE_URL: str = "https://pannaga.org.in"

    # DLT (Distributed Ledger Technology - India Telecom Mandate) & WhatsApp Templates
    DLT_ENTITY_ID: str = "1101234567890123456"
    DLT_TEMPLATE_ID_ADVISORY: str = "1107161829304123456"
    DLT_TEMPLATE_ID_ALERT: str = "1107161829304123457"
    WHATSAPP_TEMPLATE_NAME_ADVISORY: str = "monsoon_advisory_v1"
    WHATSAPP_TEMPLATE_NAME_CRITICAL: str = "monsoon_alert_critical_v1"

    # External APIs
    BHASHINI_API_KEY: str = ""
    BHASHINI_USER_ID: str = ""
    CDS_API_KEY: str = ""
    CDS_URL: str = "https://cds.climate.copernicus.eu/api/v2"

    # Climate Data Sources
    OPEN_METEO_BASE_URL: str = "https://ensemble-api.open-meteo.com/v1/ensemble"
    NOAA_ENSO_URL: str = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
    NOAA_MJO_URL: str = "https://www.cpc.ncep.noaa.gov/products/precip/CWlink/daily_mjo_index/proj_norm_mjo.txt"
    BOM_IOD_URL: str = "http://www.bom.gov.au/climate/enso/indices/iod_1.txt"
    CHIRPS_BASE_URL: str = "https://data.chc.ucsb.edu/products/CHIRPS-2.0"

    # Messaging & DLT Templates
    DLT_ONSET_TEMPLATE_ID: str = "DLT_ONSET_2026_V1"
    DLT_BREAK_TEMPLATE_ID: str = "DLT_BREAK_2026_V1"
    WHATSAPP_ONSET_TEMPLATE_NAME: str = "monsoon_onset_alert"
    WHATSAPP_BREAK_TEMPLATE_NAME: str = "monsoon_break_alert"

    # Feature Flags
    ENABLE_IMERG: bool = False
    ENABLE_SHAP: bool = True
    ENABLE_REAL_MESSAGING: bool = False
    CORS_ORIGINS: Union[List[str], str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, str) and v.startswith("["):
            return json.loads(v)
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()


def validate_production_settings(s: Settings = settings) -> None:
    """Enforce fail-fast checks in production environment."""
    if s.ENV == "production":
        if s.MESSAGING_PROVIDER not in ("twilio",):
            raise RuntimeError(
                f"Production misconfiguration: MESSAGING_PROVIDER cannot be '{s.MESSAGING_PROVIDER}' in production."
            )
        if not s.PUBLIC_BASE_URL or "localhost" in s.PUBLIC_BASE_URL or "127.0.0.1" in s.PUBLIC_BASE_URL:
            raise RuntimeError(
                "Production misconfiguration: PUBLIC_BASE_URL must be a valid non-local public URL."
            )
        if "supersecretkey" in s.SECRET_KEY or len(s.SECRET_KEY) < 32:
            raise RuntimeError(
                "Production misconfiguration: SECRET_KEY cannot use default development key."
            )
        if s.DEV_OTP_ENABLED:
            raise RuntimeError(
                "Production misconfiguration: DEV_OTP_ENABLED must be False in production."
            )

