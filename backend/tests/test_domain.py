"""Pure domain rules, ported from tests/test_business_rules.py & test_market_data.py, plus legacy parity."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from backend.app.domain import format as fmt
from backend.app.domain import indicators as ind
from backend.app.domain.new_listing import is_new_listing_history, new_listing_state
from backend.app.domain.peers import annual_comparison_row, latest_quarter_profit, ttm_net_profit
from backend.app.domain.rankings import adjust_valuation_to_close, rank_rows
from backend.app.domain.signals import fundamental_signals, technical_signals
from backend.app.domain.snapshot import compute_snapshot
from backend.app.domain.tickers import TickerFormatError, normalize_a_share, parse_any
from backend.app.domain.watchlist import summarize
from backend.app.providers.base import ReportRow

D = date


# ---------------------------------------------------------------- tickers

@pytest.mark.parametrize("raw, expected", [
    ("300308", "300308.SZ"), ("300308.SZ", "300308.SZ"), ("SZ300308", "300308.SZ"), ("sz.300308", "300308.SZ"),
    ("300308sz", "300308.SZ"), ("688525", "688525.SH"), ("sh688525", "688525.SH"), ("920190", "920190.BJ"),
    ("中际旭创(300308)", "300308.SZ"), ("中际旭创（300308.SZ）", "300308.SZ"), (" 600519 ", "600519.SH"),
])
def test_normalize_a_share(raw, expected):
    assert normalize_a_share(raw) == expected


@pytest.mark.parametrize("raw", ["30030", "AAPL", "300308.HK", ""])
def test_normalize_a_share_rejects(raw):
    with pytest.raises(TickerFormatError):
        normalize_a_share(raw)


@pytest.mark.parametrize("raw, expected", [
    ("300308", "CN:300308.SZ"), ("SZ300308", "CN:300308.SZ"), ("aapl", "US:AAPL"), ("BRK-B", "US:BRK-B"),
    ("brk.b", "US:BRK.B"), ("^GSPC", "US:^GSPC"), ("005930.KS", "KR:005930.KS"), ("000660ks", "KR:000660.KS"),
    ("091990.KQ", "KR:091990.KQ"),
])
def test_parse_any(raw, expected):
    assert parse_any(raw).id == expected


@pytest.mark.parametrize("raw", ["", "12345", "TOO-LONG-NAME", "中际旭创"])
def test_parse_any_rejects(raw):
    with pytest.raises(TickerFormatError):
        parse_any(raw)


# ---------------------------------------------------------------- watchlist summary

def test_summary_excludes_cache_old_dates_and_missing_changes():
    rows = [
        {"ticker": t, "trade_date": d, "change_pct": c, "stale": s}
        for t, d, c, s in [("a", D(2026, 9, 30), 3.0, False), ("b", D(2026, 9, 30), -1.0, False),
                           ("c", D(2026, 9, 30), 0.0, False), ("d", D(2026, 9, 30), 90.0, True),
                           ("e", D(2026, 9, 30), float("nan"), False), ("f", D(2026, 9, 29), 80.0, False)]
    ]
    summary = summarize(rows)
    assert summary["count"] == 3 and summary["average"] == pytest.approx(2 / 3)
    assert (summary["up"], summary["down"], summary["flat"]) == (1, 1, 1)
    assert summary["leader"]["ticker"] == "a" and summary["laggard"]["ticker"] == "b"
    all_stale = [{**r, "stale": True} for r in rows]
    assert summarize(all_stale)["average"] is None and summarize(all_stale)["count"] == 0
    assert summarize(rows[:1])["average"] == 3.0
    assert summarize([])["date"] is None


# ---------------------------------------------------------------- rankings

def test_rankings_sort_and_place_invalid_pe_last():
    rows = [{"t": "a", "pe_ttm": 30.0}, {"t": "b", "pe_ttm": -5.0}, {"t": "c", "pe_ttm": 10.0},
            {"t": "d", "pe_ttm": None}, {"t": "e", "pe_ttm": 10.0}, {"t": "f", "pe_ttm": 0.0}]
    ranked = rank_rows(rows, "pe_ttm")
    assert [r["t"] for r in ranked] == ["c", "e", "a", "b", "d", "f"]
    assert [r["rank"] for r in ranked] == [1, 1, 3, 4, 4, 4]


def test_rankings_descending_with_competition_ranks():
    rows = [{"t": "a", "amount": 5.0}, {"t": "b", "amount": 9.0}, {"t": "c", "amount": 9.0}, {"t": "d", "amount": None}]
    ranked = rank_rows(rows, "amount")
    assert [(r["t"], r["rank"]) for r in ranked] == [("b", 1), ("c", 1), ("a", 3), ("d", 4)]
    with pytest.raises(ValueError):
        rank_rows(rows, "nope")


def test_valuation_adjusted_to_completed_close():
    assert adjust_valuation_to_close(30.0, 110.0, 100.0) == pytest.approx(27.2727, rel=1e-4)
    assert adjust_valuation_to_close(30.0, None, 100.0) == 30.0
    assert adjust_valuation_to_close(None, 110.0, 100.0) is None


# ---------------------------------------------------------------- new listing

def test_first_day_listing_uses_safe_guards():
    state = new_listing_state(pd.Series([49.0]), rsi_period=14)
    assert state.daily_bars == 1 and state.previous_close is None
    assert not any([state.trend_ready, state.rsi_ready, state.macd_ready, state.volatility_ready])


def test_new_listing_history_detection():
    assert is_new_listing_history(D(2026, 6, 1), D(2026, 1, 1))
    assert not is_new_listing_history(D(2026, 1, 5), D(2026, 1, 1))
    assert not is_new_listing_history(None, D(2026, 1, 1))


# ---------------------------------------------------------------- peers / financial rows

def _rows(*items):
    return [ReportRow(p, t, m, v, None) for p, t, m, v in items]


def test_peer_row_uses_latest_annual_report_and_calculates_margin():
    rows = _rows(
        (D(2023, 12, 31), "annual", "revenue", 100e8), (D(2023, 12, 31), "annual", "net_profit", 10e8),
        (D(2024, 9, 30), "q3", "revenue", 90e8), (D(2024, 9, 30), "q3", "net_profit", 12e8),
        (D(2024, 12, 31), "annual", "revenue", 200e8), (D(2024, 12, 31), "annual", "net_profit", 30e8),
        (D(2024, 12, 31), "annual", "debt_ratio", 42.5), (D(2024, 12, 31), "annual", "capex", 20e8),
    )
    row = annual_comparison_row({"name": "示例公司"}, rows)
    assert row["period_end"] == D(2024, 12, 31)
    assert (row["revenue"], row["net_profit"], row["net_margin"]) == (200e8, 30e8, 15.0)
    assert row["debt_ratio"] == 42.5 and row["capex"] == 20e8 and row["capex_ratio"] == 10.0


def test_ttm_profit_replaces_prior_year_comparable_cumulative_profit():
    rows = _rows((D(2025, 12, 31), "annual", "net_profit", 100.0), (D(2025, 9, 30), "q3", "net_profit", 70.0),
                 (D(2026, 9, 30), "q3", "net_profit", 90.0), (D(2026, 6, 30), "h1", "net_profit", 50.0))
    assert ttm_net_profit(rows) == 120.0
    assert latest_quarter_profit(rows)["period_end"] == D(2026, 9, 30)
    assert ttm_net_profit(rows[:1]) is None


# ---------------------------------------------------------------- snapshot (B1) / signals (B3, B10)

def _bars(n, start="2025-01-01"):
    index = [d.date() for d in pd.bdate_range(start, periods=n)]
    close = pd.Series(np.linspace(10, 20, n), index=index)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1, "close": close,
                         "volume": 1000.0, "amount": close * 1000})


def test_snapshot_separates_range_and_52_week_extremes():
    year = _bars(250)
    display = year.iloc[-20:]
    state = new_listing_state(year["close"], 14)
    snap = compute_snapshot(display, year, state)
    assert snap.range_low == pytest.approx(display["low"].min()) and snap.low_52w == pytest.approx(year["low"].min())
    assert snap.range_low > snap.low_52w
    assert snap.max_amount_date == display.index[-1]
    with_intraday = compute_snapshot(display, year, state, intraday_price=21.0, intraday_pre_close=20.0)
    assert with_intraday.change_pct == pytest.approx(5.0) and with_intraday.price_from_intraday


def test_signals_are_descriptive_without_advice():
    bars = _bars(80)
    close = bars["close"]
    macd = ind.macd(close)
    state = new_listing_state(close, 14)
    signals = technical_signals(close, ind.ma(close, 20), ind.rsi(close, 14), 14, macd["macd"], macd["signal"], 45.0, state)
    signals += fundamental_signals(None, [])
    text = " ".join(f"{s.status}{s.description}" for s in signals)
    for banned in ("买入", "卖出", "建仓", "减仓", "看涨", "看跌", "评分"):
        assert banned not in text
    assert [s.key for s in signals] == ["trend", "rsi", "macd", "volatility", "debt_ratio", "capex"]
    assert signals[0].status == "高于均线"


def test_trend_signal_uses_full_series_ma20_not_display_slice():
    """B10: with 5 bars displayed, the MA20 must still come from the warm-up-inclusive series."""
    close = pd.Series([10.0] * 30 + [20.0, 9.0, 9.0, 9.0, 9.0])
    full_ma20 = ind.ma(close, 20)
    state = new_listing_state(close, 14)
    signal = technical_signals(close.iloc[-5:], full_ma20, ind.rsi(close, 14), 14, close * 0, close * 0, 10.0, state)[0]
    assert signal.status == "低于均线"  # 9 < MA20 (≈10.05); a 5-bar mean (11.2) would mislead


# ---------------------------------------------------------------- indicators

def test_warmup_covers_longest_indicator():
    params = ind.IndicatorParams(ma=(5, 120), bbi=True, boll=True, rsi=14)
    assert params.required_sessions == 120
    start = ind.warmup_start(D(2026, 6, 1), params)
    assert len(pd.bdate_range(start, D(2026, 6, 1))) - 1 == 135


@pytest.mark.parametrize("value, market, expected", [
    (15000, "CN", "1.50万股"), (1.5e8, "CN", "1.50亿股"), (2.5e6, "US", "2.50M股"), (None, "CN", "—"),
])
def test_format_volume(value, market, expected):
    assert fmt.format_volume(value, market) == expected


@pytest.mark.parametrize("value, market, expected", [
    (1.5e8, "CN", "1.50亿元"), (2e12, "KR", "2.00万亿韩元"), (3.2e9, "US", "3.20B美元"), (float("nan"), "US", "—"),
])
def test_format_amount(value, market, expected):
    assert fmt.format_amount(value, market) == expected
