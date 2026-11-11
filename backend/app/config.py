"""Backend settings (environment variables prefixed with STOCK_INSIGHT_)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STOCK_INSIGHT_", env_file=".env", extra="ignore")

    db_path: Path = REPO_ROOT / "data" / "stock_insight.db"
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"
    demo_mode: bool = False
    request_timeout_s: float = 20.0
    min_request_interval_s: float = 0.3
    # Provider keys to skip (ths / eastmoney / yahoo / stooq), e.g. STOCK_INSIGHT_DISABLED_PROVIDERS='["ths"]'
    disabled_providers: list[str] = []
    # Stooq now serves a bot-verification page instead of CSV (docs/plan-b-draft.md §4.1 item 6).
    stooq_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
