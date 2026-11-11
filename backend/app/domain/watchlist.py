"""Watchlist summary (ported from watchlist.summarize_watchlist)."""
from __future__ import annotations

import math


def summarize(rows: list[dict]) -> dict:
    """Count only rows on the newest trade date that are not stale and have a finite change.

    ``rows`` need ``trade_date`` (date | None), ``change_pct`` and ``stale``.
    """
    dates = [r["trade_date"] for r in rows if r.get("trade_date")]
    latest = max(dates) if dates else None
    valid = [r for r in rows if latest and r.get("trade_date") == latest and not r.get("stale")
             and r.get("change_pct") is not None and math.isfinite(r["change_pct"])]
    values = [r["change_pct"] for r in valid]
    return {
        "date": latest,
        "count": len(valid),
        "total": len(rows),
        "average": sum(values) / len(values) if values else None,
        "up": sum(v > 0 for v in values),
        "down": sum(v < 0 for v in values),
        "flat": sum(v == 0 for v in values),
        "leader": max(valid, key=lambda r: r["change_pct"]) if valid else None,
        "laggard": min(valid, key=lambda r: r["change_pct"]) if valid else None,
    }
