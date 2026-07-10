"""Batch A-share market snapshots and deterministic stock-pool rankings.

The public functions in this module deliberately operate on a flattened stock
universe so the data layer stays independent from Streamlit. Eastmoney's
``ulist.np/get`` endpoint is called in two bounded batches; missing rows are
filled from the last atomic on-disk snapshot instead of triggering N
single-security requests.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from curl_cffi.const import CurlHttpVersion
from curl_cffi import requests


EASTMONEY_BATCH_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
CACHE_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "cache"
    / "a_share_market_snapshot.csv"
)
CHINA_TZ = ZoneInfo("Asia/Shanghai")

SNAPSHOT_COLUMNS = [
    "industry",
    "name",
    "ticker",
    "price",
    "previous_close",
    "change_pct",
    "amount",
    "market_cap",
    "pe_ttm",
    "quote_time",
    "trade_date",
    "stale",
]
NUMERIC_COLUMNS = [
    "price",
    "previous_close",
    "change_pct",
    "amount",
    "market_cap",
    "pe_ttm",
]
RANK_METRICS = ("change_pct", "amount", "market_cap", "pe_ttm")

_CACHE_LOCK = threading.RLock()
_TICKER_PATTERN = re.compile(r"^\d{6}\.(?:SH|SZ|BJ)$")


class MarketSnapshotError(RuntimeError):
    """Raised when neither a live batch quote nor a local snapshot is usable."""


def flatten_a_share_universe(universe) -> list[dict]:
    """Flatten ``{industry: [(name, ticker), ...]}`` into stable row dicts.

    The insertion order of industries and securities is preserved. Duplicate
    tickers are rejected because a ranking row must map to exactly one stock.
    """

    if not isinstance(universe, Mapping):
        raise TypeError("universe must be a mapping of industries to securities")

    rows: list[dict] = []
    seen: set[str] = set()
    for industry, securities in universe.items():
        for security in securities:
            if isinstance(security, Mapping):
                name = security.get("name")
                ticker = security.get("ticker")
            else:
                try:
                    name, ticker = security
                except (TypeError, ValueError) as error:
                    raise ValueError(
                        "each universe entry must contain a name and ticker"
                    ) from error

            normalized_ticker = str(ticker).strip().upper()
            if not _TICKER_PATTERN.fullmatch(normalized_ticker):
                raise ValueError(f"invalid A-share ticker: {ticker!r}")
            if normalized_ticker in seen:
                raise ValueError(f"duplicate A-share ticker: {normalized_ticker}")
            seen.add(normalized_ticker)
            rows.append(
                {
                    "industry": str(industry),
                    "name": str(name),
                    "ticker": normalized_ticker,
                }
            )
    return rows


def _normalize_universe_rows(universe_rows) -> list[dict]:
    if isinstance(universe_rows, Mapping):
        return flatten_a_share_universe(universe_rows)
    if isinstance(universe_rows, (str, bytes)) or not isinstance(
        universe_rows, Sequence
    ):
        raise TypeError("universe_rows must be a sequence of row mappings")

    rows: list[dict] = []
    seen: set[str] = set()
    for row in universe_rows:
        if not isinstance(row, Mapping):
            raise TypeError("each flattened universe row must be a mapping")
        missing = {"industry", "name", "ticker"}.difference(row)
        if missing:
            raise ValueError(
                f"universe row is missing required fields: {', '.join(sorted(missing))}"
            )
        ticker = str(row["ticker"]).strip().upper()
        if not _TICKER_PATTERN.fullmatch(ticker):
            raise ValueError(f"invalid A-share ticker: {ticker!r}")
        if ticker in seen:
            raise ValueError(f"duplicate A-share ticker: {ticker}")
        seen.add(ticker)
        rows.append(
            {
                "industry": str(row["industry"]),
                "name": str(row["name"]),
                "ticker": ticker,
            }
        )
    return rows


def _clear_broken_local_proxy() -> None:
    """Mirror the application's handling of its known dead loopback proxy."""

    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        value = os.environ.get(name)
        if not value:
            continue
        parsed = urlparse(value if "://" in value else f"http://{value}")
        if parsed.hostname in {"127.0.0.1", "localhost", "::1"} and parsed.port == 9:
            os.environ.pop(name, None)


def _eastmoney_secid(ticker: str) -> str:
    code, suffix = ticker.split(".", maxsplit=1)
    # Eastmoney uses market 1 for Shanghai and market 0 for both Shenzhen and
    # Beijing securities (including the new 920xxx Beijing codes).
    market = "1" if suffix == "SH" else "0"
    return f"{market}.{code}"


def _as_number(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return np.nan
    return number if np.isfinite(number) else np.nan


def _china_now() -> datetime:
    return datetime.now(CHINA_TZ)


def _format_quote_time(value) -> str | None:
    number = _as_number(value)
    if np.isfinite(number) and number > 0:
        if number > 10_000_000_000:
            number /= 1000
        return datetime.fromtimestamp(number, tz=CHINA_TZ).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    if value in (None, "", "-"):
        return None
    try:
        timestamp = pd.Timestamp(value)
        if timestamp.tzinfo is None:
            timestamp = timestamp.tz_localize(CHINA_TZ)
        else:
            timestamp = timestamp.tz_convert(CHINA_TZ)
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def _format_trade_date(value, quote_time: str | None = None) -> str | None:
    if value not in (None, "", "-"):
        try:
            digits = str(int(float(value)))
            if len(digits) == 8:
                return datetime.strptime(digits, "%Y%m%d").strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            try:
                return pd.Timestamp(value).strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                pass
    return quote_time[:10] if quote_time else None


def _latest_completed_close(
    price: float,
    previous_close: float,
    trade_date: str | None,
    now: datetime,
) -> float:
    """Return the close of the latest completed China-market daily bar."""

    market_now = now.astimezone(CHINA_TZ)
    today = market_now.date().isoformat()
    before_close = market_now.time().replace(tzinfo=None) < datetime.strptime(
        "15:00", "%H:%M"
    ).time()
    if trade_date == today and before_close and np.isfinite(previous_close):
        return previous_close
    if np.isfinite(price):
        return price
    return previous_close


def _adjust_valuation_to_close(
    value: float,
    current_price: float,
    completed_close: float,
) -> float:
    if not np.isfinite(value):
        return np.nan
    if (
        not np.isfinite(current_price)
        or current_price <= 0
        or not np.isfinite(completed_close)
        or completed_close <= 0
    ):
        return value
    return value * completed_close / current_price


def _request_market_rows(rows: list[dict]) -> list[dict]:
    """Fetch the universe in bounded Eastmoney batch requests.

    Eastmoney currently closes oversized ``ulist.np`` connections before a
    response is written.  A maximum of 43 securities keeps the 86-stock pool
    to two requests while retaining the provider's batch semantics.
    """

    _clear_broken_local_proxy()
    session = requests.Session(impersonate="chrome", trust_env=False)
    result: list[dict] = []
    errors: list[Exception] = []
    for offset in range(0, len(rows), 43):
        chunk = rows[offset : offset + 43]
        params = {
            "fltt": "2",
            "invt": "2",
            "fields": "f12,f14,f2,f18,f3,f6,f20,f115,f124,f297",
            "secids": ",".join(_eastmoney_secid(row["ticker"]) for row in chunk),
        }
        chunk_error: Exception | None = None
        for _attempt in range(2):
            try:
                response = session.get(
                    EASTMONEY_BATCH_URL,
                    params=params,
                    headers={
                        "Referer": "https://quote.eastmoney.com/",
                        "Connection": "close",
                    },
                    http_version=CurlHttpVersion.V1_1,
                    timeout=20,
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("rc") != 0:
                    raise MarketSnapshotError(
                        f"Eastmoney returned quote error rc={payload.get('rc')!r}"
                    )
                data = payload.get("data") or {}
                diff = data.get("diff") or []
                if isinstance(diff, Mapping):
                    diff = list(diff.values())
                if not isinstance(diff, list):
                    raise MarketSnapshotError(
                        "Eastmoney returned an unexpected quote schema"
                    )
                result.extend(item for item in diff if isinstance(item, Mapping))
                chunk_error = None
                break
            except Exception as error:
                chunk_error = error
        if chunk_error is not None:
            errors.append(chunk_error)

    try:
        session.close()
    except Exception:
        pass

    if not result and errors:
        raise MarketSnapshotError("every Eastmoney quote batch failed") from errors[0]
    return result


def _parse_live_rows(raw_rows: list[dict], now: datetime) -> dict[str, dict]:
    parsed: dict[str, dict] = {}
    for raw in raw_rows:
        code = str(raw.get("f12", "")).strip()
        if not code:
            continue
        price = _as_number(raw.get("f2"))
        previous_close = _as_number(raw.get("f18"))
        change_pct = _as_number(raw.get("f3"))
        if (
            not np.isfinite(change_pct)
            and np.isfinite(price)
            and np.isfinite(previous_close)
            and previous_close != 0
        ):
            change_pct = (price / previous_close - 1) * 100

        quote_time = _format_quote_time(raw.get("f124"))
        trade_date = _format_trade_date(raw.get("f297"), quote_time)
        completed_close = _latest_completed_close(
            price, previous_close, trade_date, now
        )
        market_cap = _adjust_valuation_to_close(
            _as_number(raw.get("f20")), price, completed_close
        )
        pe_ttm = _adjust_valuation_to_close(
            _as_number(raw.get("f115")), price, completed_close
        )
        parsed[code] = {
            "provider_name": raw.get("f14"),
            "price": price,
            "previous_close": previous_close,
            "change_pct": change_pct,
            "amount": _as_number(raw.get("f6")),
            "market_cap": market_cap,
            "pe_ttm": pe_ttm,
            "quote_time": quote_time,
            "trade_date": trade_date,
            "stale": False,
        }
    return parsed


def _coerce_stale(value) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _coerce_snapshot_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in SNAPSHOT_COLUMNS:
        if column not in result:
            result[column] = False if column == "stale" else np.nan
    result = result[SNAPSHOT_COLUMNS]
    for column in NUMERIC_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["stale"] = result["stale"].map(_coerce_stale).astype(bool)
    for column in ("industry", "name", "ticker", "quote_time", "trade_date"):
        result[column] = result[column].where(result[column].notna(), None)
    return result


def _load_snapshot_cache() -> pd.DataFrame:
    with _CACHE_LOCK:
        if not CACHE_PATH.exists():
            return pd.DataFrame(columns=SNAPSHOT_COLUMNS)
        try:
            cached = pd.read_csv(CACHE_PATH, encoding="utf-8-sig")
            return _coerce_snapshot_frame(cached)
        except (OSError, ValueError, pd.errors.ParserError):
            return pd.DataFrame(columns=SNAPSHOT_COLUMNS)


def _save_snapshot_cache(frame: pd.DataFrame) -> None:
    """Atomically replace the cache so readers never observe a partial CSV."""

    snapshot = _coerce_snapshot_frame(frame)
    cache_dir = CACHE_PATH.parent
    with _CACHE_LOCK:
        cache_dir.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8-sig",
                newline="",
                prefix=f".{CACHE_PATH.stem}.",
                suffix=".tmp",
                dir=cache_dir,
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                snapshot.to_csv(handle, index=False)
                handle.flush()
            os.replace(temp_path, CACHE_PATH)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)


def _cache_row_is_usable(row: Mapping) -> bool:
    quote_time = row.get("quote_time")
    trade_date = row.get("trade_date")
    if quote_time is not None and pd.notna(quote_time) and str(quote_time).strip():
        return True
    if trade_date is not None and pd.notna(trade_date) and str(trade_date).strip():
        return True
    return any(np.isfinite(_as_number(row.get(column))) for column in NUMERIC_COLUMNS)


def _cached_by_ticker(cached: pd.DataFrame) -> dict[str, dict]:
    result: dict[str, dict] = {}
    if cached.empty:
        return result
    for record in cached.to_dict("records"):
        ticker = str(record.get("ticker", "")).strip().upper()
        if ticker and _cache_row_is_usable(record):
            result[ticker] = record
    return result


def _merge_snapshot_rows(
    universe_rows: list[dict],
    live_by_code: dict[str, dict],
    cached_by_ticker: dict[str, dict],
) -> pd.DataFrame:
    records = []
    for universe_row in universe_rows:
        ticker = universe_row["ticker"]
        code = ticker.split(".", maxsplit=1)[0]
        if code in live_by_code:
            quote = dict(live_by_code[code])
            quote.pop("provider_name", None)
            stale = False
        elif ticker in cached_by_ticker:
            cached = cached_by_ticker[ticker]
            quote = {column: cached.get(column) for column in SNAPSHOT_COLUMNS[3:-1]}
            stale = True
        else:
            quote = {column: np.nan for column in NUMERIC_COLUMNS}
            quote.update({"quote_time": None, "trade_date": None})
            stale = True
        records.append({**universe_row, **quote, "stale": stale})
    return _coerce_snapshot_frame(pd.DataFrame(records))


def fetch_a_share_market_snapshot(universe_rows) -> pd.DataFrame:
    """Fetch the whole A-share universe in one batch with cache fallback.

    ``market_cap`` and ``pe_ttm`` are normalized to the close of the latest
    completed daily bar. Before 15:00 on the current trading date that means
    yesterday's close; after the close and on non-trading days it means the
    latest price returned by Eastmoney.
    """

    rows = _normalize_universe_rows(universe_rows)
    if not rows:
        return pd.DataFrame(columns=SNAPSHOT_COLUMNS)

    cached = _load_snapshot_cache()
    cached_by_ticker = _cached_by_ticker(cached)
    request_error: Exception | None = None
    try:
        raw_rows = _request_market_rows(rows)
        live_by_code = _parse_live_rows(raw_rows, _china_now())
    except Exception as error:
        request_error = error
        live_by_code = {}

    requested_codes = {row["ticker"].split(".", maxsplit=1)[0] for row in rows}
    live_by_code = {
        code: quote for code, quote in live_by_code.items() if code in requested_codes
    }
    if not live_by_code:
        matching_cache = {
            row["ticker"]: cached_by_ticker[row["ticker"]]
            for row in rows
            if row["ticker"] in cached_by_ticker
        }
        if not matching_cache:
            message = "A-share market snapshot is unavailable and no cache exists"
            if request_error is not None:
                raise MarketSnapshotError(message) from request_error
            raise MarketSnapshotError(message)
        result = _merge_snapshot_rows(rows, {}, matching_cache)
        result.attrs.update(
            {
                "source": "local cache",
                "live_count": 0,
                "stale_count": int(result["stale"].sum()),
                "fallback_reason": str(request_error) if request_error else "empty response",
            }
        )
        return result

    result = _merge_snapshot_rows(rows, live_by_code, cached_by_ticker)
    _save_snapshot_cache(result)
    result.attrs.update(
        {
            "source": "Eastmoney",
            "live_count": len(live_by_code),
            "stale_count": int(result["stale"].sum()),
        }
    )
    return result


def rank_snapshot(frame: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Return all snapshot rows in a deterministic ranking for ``metric``.

    Equal values receive competition ranks (``1, 1, 3``), and their input
    order is preserved. Missing values are placed last. For ``pe_ttm`` only
    positive values participate; zero, negative and missing PE values share
    the final bucket at the bottom.
    """

    if metric not in RANK_METRICS:
        raise ValueError(
            f"metric must be one of {', '.join(RANK_METRICS)}; got {metric!r}"
        )
    if metric not in frame.columns:
        raise ValueError(f"snapshot is missing metric column: {metric}")

    ranked = frame.copy().reset_index(drop=True)
    values = pd.to_numeric(ranked[metric], errors="coerce")
    valid = values.notna()
    ascending = metric == "pe_ttm"
    if metric == "pe_ttm":
        valid &= values > 0

    ranked[metric] = values
    ranked["_invalid_metric"] = ~valid
    ranked["_sort_value"] = values.where(valid)
    ranked["_universe_order"] = np.arange(len(ranked))
    ranked = ranked.sort_values(
        by=["_invalid_metric", "_sort_value", "_universe_order"],
        ascending=[True, ascending, True],
        kind="mergesort",
        na_position="last",
    )

    competition_rank = values.where(valid).rank(
        method="min", ascending=ascending
    )
    competition_rank.loc[~valid] = int(valid.sum()) + 1
    ranked["rank"] = competition_rank.reindex(ranked.index).astype("Int64")
    ranked = ranked.drop(
        columns=["_invalid_metric", "_sort_value", "_universe_order"]
    )
    columns = ["rank", *[column for column in ranked.columns if column != "rank"]]
    return ranked[columns].reset_index(drop=True)


def build_rankings(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build the four stock-pool rankings from one market snapshot."""

    return {metric: rank_snapshot(frame, metric) for metric in RANK_METRICS}
