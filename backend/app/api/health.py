"""Health endpoint: reports per-provider status (filled in from fetch_log in P2)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["系统"])


class ProviderStatus(BaseModel):
    name: str
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error: str | None = None


class HealthResponse(BaseModel):
    status: str
    time: datetime
    providers: list[ProviderStatus]


@router.get("/health", response_model=HealthResponse, summary="数据源状态")
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        time=datetime.now(timezone.utc),
        providers=[ProviderStatus(name=name) for name in ("同花顺", "东方财富", "Yahoo", "Stooq")],
    )
