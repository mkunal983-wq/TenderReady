from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"), extra="ignore"
    )
    database_url: str = "sqlite:///./tenderready.db"
    app_env: Literal["development", "production"] = "development"
    nebius_api_key: SecretStr = SecretStr("")
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1"
    nebius_model: str = "nvidia/nemotron-3-super-120b-a12b"
    nebius_json_mode: bool = False
    nebius_timeout_seconds: float = Field(default=60, gt=0, le=180)
    nebius_max_output_tokens: int = Field(default=8192, ge=128, le=16384)
    storage_dir: Path = PROJECT_ROOT / "data" / "documents"
    upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)
    pdf_max_pages: int = Field(default=40, ge=1, le=100)
    pdf_max_text_chars: int = Field(default=160000, ge=1000, le=500000)
    pdf_parse_timeout_seconds: int = Field(default=20, ge=1, le=60)
    analysis_timeout_seconds: int = Field(default=600, ge=1, le=1800)
    app_api_token: SecretStr = SecretStr("")
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @model_validator(mode="after")
    def validate_access_configuration(self):
        if self.app_env == "production" and len(self.app_api_token.get_secret_value()) < 32:
            raise ValueError("Production requires APP_API_TOKEN with at least 32 characters.")
        if "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must contain explicit origins, not a wildcard.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
