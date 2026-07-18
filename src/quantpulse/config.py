"""Central application settings, loaded from environment variables / .env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore", frozen=True)

    database_url: str = "postgresql+psycopg://quantpulse:quantpulse@localhost:5432/market"
    mlflow_tracking_uri: str = "http://localhost:5000"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    quantpulse_universe_file: Path = Path("configs/universe.yaml")
    quantpulse_history_start: str = "2018-01-01"


@lru_cache
def get_settings() -> Settings:
    return Settings()
