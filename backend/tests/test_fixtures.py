"""Sanity checks for the recorded golden samples (offline).

These do not test the new providers (they arrive in P1); they pin down that the
fixtures are real, parseable payloads and encode the measured facts from
docs/plan-b-draft.md §4.1 so the P1 parsers have something concrete to match.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


def _jsonp(path: str) -> dict:
    text = (FIXTURES / path).read_text(encoding="utf-8")
    return json.loads(text[text.find("(") + 1 : text.rfind(")")])


def _ths_daily(path: str) -> dict[str, list[str]]:
    rows = {}
    for raw in _jsonp(path)["data"].split(";"):
        values = raw.split(",")
        if len(values) >= 7:
            rows[values[0]] = values
    return rows


def _em_klines(path: str) -> dict[str, list[str]]:
    data = json.loads((FIXTURES / path).read_text(encoding="utf-8"))["data"]
    return {line.split(",")[0].replace("-", ""): line.split(",") for line in data["klines"]}


@pytest.mark.parametrize("name", sorted(MANIFEST))
def test_manifest_entry_has_file(name):
    entry = MANIFEST[name]
    path = FIXTURES / entry["file"]
    assert path.is_file(), entry["file"]
    assert path.stat().st_size == entry["bytes"]
    assert b"/__verify" not in path.read_bytes()


@pytest.mark.parametrize("code", ["300308", "920190"])
def test_eastmoney_volume_is_lots_and_ths_is_shares(code):
    """§4.1 finding 2: 东方财富 A 股成交量单位是"手"，同花顺是"股"（×100）."""
    ths = _ths_daily(next(e["file"] for e in MANIFEST.values() if e["file"].startswith(f"ths/daily_{code}_")))
    em = _em_klines(f"eastmoney/kline_0.{code}.json")
    # Skip the newest common day: THS's "today" row may be stale (§4.1 finding 4).
    common = sorted(set(ths) & set(em))[:-1]
    assert len(common) >= 20
    ratios = [float(ths[d][5]) / float(em[d][5]) for d in common if float(em[d][5]) > 0]
    assert all(95 <= r <= 105 for r in ratios), ratios[:5]


@pytest.mark.parametrize("code", ["300308", "920190"])
def test_ths_and_eastmoney_qfq_closes_agree_on_history(code):
    """Both feeds are 前复权; historical closes should match to 0.1%."""
    ths = _ths_daily(next(e["file"] for e in MANIFEST.values() if e["file"].startswith(f"ths/daily_{code}_")))
    em = _em_klines(f"eastmoney/kline_0.{code}.json")
    common = sorted(set(ths) & set(em))[:-1]
    for day in common:
        ths_close, em_close = float(ths[day][4]), float(em[day][2])
        assert abs(ths_close - em_close) / em_close < 0.001, (day, ths_close, em_close)


def test_beijing_exchange_intraday_is_available():
    """§4.1 finding 1: 北交所 920190 可从同花顺公开分时取数."""
    quote = _jsonp("ths/intraday_920190.js")["hs_920190"]
    assert quote["pre"] and len(quote["data"].split(";")) > 10


def test_eastmoney_snapshot_covers_all_boards():
    diff = json.loads((FIXTURES / "eastmoney/ulist_snapshot.json").read_text(encoding="utf-8"))["data"]["diff"]
    assert {row["f12"] for row in diff} == {"300308", "600519", "000001", "920190", "688525"}


def test_ths_finance_page_has_main_payload():
    html = (FIXTURES / "ths/finance_300308.html").read_bytes().decode("gb18030", errors="ignore")
    match = re.search(r'<p\s+id="main">\s*(.*?)\s*</p>', html, flags=re.S)
    assert match
    payload = json.loads(match.group(1))
    assert payload["report"][0]


def test_yahoo_charts_have_bars():
    for name in ("chart_daily_AAPL.json", "chart_daily_005930.KS.json", "chart_5m_AAPL.json", "chart_KRW=X.json"):
        result = json.loads((FIXTURES / "yahoo" / name).read_text(encoding="utf-8"))["chart"]["result"][0]
        assert len(result["timestamp"]) >= 3, name
