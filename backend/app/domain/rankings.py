"""Stock-pool ranking (ported from market_snapshot.rank_snapshot / _adjust_valuation_to_close)."""
from __future__ import annotations

import math

RANK_METRICS = ("change_pct", "amount", "market_cap", "pe_ttm", "quarter_profit")


def _valid(metric: str, value) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return value > 0 if metric == "pe_ttm" else True


def rank_rows(rows: list[dict], metric: str) -> list[dict]:
    """Competition ranks (1, 1, 3); input order breaks ties; invalid values (and PE ≤ 0) share the last bucket.

    PE ranks ascending (lower first); every other metric descending.
    """
    if metric not in RANK_METRICS:
        raise ValueError(f"metric must be one of {', '.join(RANK_METRICS)}; got {metric!r}")
    ascending = metric == "pe_ttm"
    indexed = list(enumerate(rows))
    valid = [(i, r) for i, r in indexed if _valid(metric, r.get(metric))]
    invalid = [(i, r) for i, r in indexed if not _valid(metric, r.get(metric))]
    valid.sort(key=lambda item: (item[1][metric] if ascending else -item[1][metric], item[0]))
    ranked: list[dict] = []
    previous, previous_rank = object(), 0
    for position, (_, row) in enumerate(valid, start=1):
        rank = previous_rank if row[metric] == previous else position
        ranked.append({**row, "rank": rank})
        previous, previous_rank = row[metric], rank
    ranked.extend({**row, "rank": len(valid) + 1} for _, row in invalid)
    return ranked


def adjust_valuation_to_close(value: float | None, current_price: float | None, completed_close: float | None) -> float | None:
    """Scale an intraday-priced valuation (PE, market cap) to the latest completed close."""
    if value is None:
        return None
    if not current_price or current_price <= 0 or not completed_close or completed_close <= 0:
        return value
    return value * completed_close / current_price
