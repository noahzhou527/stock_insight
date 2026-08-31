import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd
import numpy as np

from a_share_universe import A_SHARE_UNIVERSE
from data_fetcher import _filter_suspicious_korean_daily_bars, _standardize_price_frame
from market_snapshot import (
    _request_market_rows,
    flatten_a_share_universe,
    rank_snapshot,
)
from services import market_overview_data as overview
from services.market_data import merge_intraday_daily_bar


class _FailingSession:
    def get(self, *_args, **_kwargs):
        raise RuntimeError("temporary Eastmoney connection failure")

    def close(self):
        return None


class _MarketRowsResponse:
    def __init__(self, diff):
        self._diff = diff

    def raise_for_status(self):
        return None

    def json(self):
        return {"rc": 0, "data": {"diff": self._diff}}


class _MarketRowsSession:
    def __init__(self):
        self.calls = []

    def get(self, _url, params, **_kwargs):
        secids = params["secids"].split(",")
        self.calls.append(secids)
        return _MarketRowsResponse([{"f12": secid.split(".")[1]} for secid in secids])


class MarketOverviewDataTests(unittest.TestCase):
    def test_price_standardization_estimates_missing_daily_amount(self):
        frame = _standardize_price_frame(
            pd.DataFrame(
                [{"Date": "2026-07-10", "Open": 1, "High": 2, "Low": 0.5, "Close": 1.5, "Volume": 100}]
            )
        )

        self.assertEqual(frame.iloc[0]["Amount"], 150)

    def test_korean_history_drops_an_implausible_placeholder_volume(self):
        frame = pd.DataFrame(
            {"Volume": [30_000_000, 31_000_000, 1_191, 29_000_000, 32_000_000]},
            index=pd.date_range("2026-06-08", periods=5, freq="D"),
        )

        filtered = _filter_suspicious_korean_daily_bars(frame)

        self.assertNotIn(pd.Timestamp("2026-06-10"), filtered.index)
        self.assertEqual(filtered.attrs["filtered_suspicious_daily_bars"], 1)

    @patch("services.market_overview_data._ths_intraday")
    @patch("services.market_overview_data._ths_daily")
    def test_cn_index_uses_latest_completed_amount_and_comparison(self, mock_daily, mock_intraday):
        today = pd.Timestamp.now(tz=ZoneInfo("Asia/Shanghai")).tz_localize(None).normalize()
        mock_daily.return_value = pd.DataFrame(
            {"Close": [100.0, 105.0], "Amount": [100_000_000.0, 120_000_000.0]},
            index=[today - pd.Timedelta(days=2), today - pd.Timedelta(days=1)],
        )
        mock_intraday.side_effect = overview.DataFetchError("unavailable", "no intraday")
        result = overview.fetch_cn_index({"name": "测试指数", "symbol": "1A0001", "display_code": "000001"})
        self.assertEqual(result["amount"], 120_000_000.0)
        self.assertEqual(result["previous_amount"], 100_000_000.0)
        self.assertEqual(result["amount_change"], 20_000_000.0)
        self.assertEqual(result["amount_change_pct"], 20.0)

    @patch("services.market_overview_data.time.sleep")
    @patch("services.market_overview_data.requests.Session", return_value=_FailingSession())
    def test_cn_breadth_keeps_last_successful_snapshot_when_eastmoney_fails(self, _mock_session, _sleep):
        previous = overview._LAST_CN_MARKET_BREADTH
        overview._LAST_CN_MARKET_BREADTH = {"up": 10, "flat": 2, "down": 8, "total": 20, "source": "东方财富全 A 股快照"}
        try:
            breadth = overview.fetch_cn_market_breadth()
        finally:
            overview._LAST_CN_MARKET_BREADTH = previous
        self.assertTrue(breadth["stale"])
        self.assertEqual(breadth["up"], 10)
        self.assertIn("上次成功快照", breadth["source"])

    @patch("services.market_overview_data.time.sleep")
    @patch("services.market_overview_data.requests.Session", return_value=_FailingSession())
    def test_cn_breadth_does_not_mislabel_watchlist_as_full_market(self, _mock_session, _sleep):
        previous = overview._LAST_CN_MARKET_BREADTH
        overview._LAST_CN_MARKET_BREADTH = None
        try:
            with self.assertRaises(overview.DataFetchError):
                overview.fetch_cn_market_breadth()
        finally:
            overview._LAST_CN_MARKET_BREADTH = previous

class CurrentDailyBarTests(unittest.TestCase):
    def test_appends_latest_intraday_session_as_daily_bar(self):
        historical = pd.DataFrame(
            {
                "Open": [10.0],
                "High": [11.0],
                "Low": [9.0],
                "Close": [10.5],
                "Volume": [100.0],
            },
            index=pd.to_datetime(["2026-07-24"]),
        )
        intraday = pd.DataFrame(
            {
                "Price": [20.0, 22.0, 21.0],
                "Volume": [10.0, 20.0, 30.0],
                "Amount": [200.0, 440.0, 630.0],
            },
            index=pd.to_datetime(
                ["2026-07-27 09:30", "2026-07-27 10:00", "2026-07-27 10:30"]
            ),
        )
        intraday.attrs["trade_date"] = "2026-07-27"
        intraday.attrs["symbol_name"] = "C长鑫"

        result = merge_intraday_daily_bar(historical, intraday, "2026-07-27")

        self.assertEqual(result.index[-1], pd.Timestamp("2026-07-27"))
        self.assertEqual(result.iloc[-1]["Open"], 20.0)
        self.assertEqual(result.iloc[-1]["High"], 22.0)
        self.assertEqual(result.iloc[-1]["Low"], 20.0)
        self.assertEqual(result.iloc[-1]["Close"], 21.0)
        self.assertEqual(result.iloc[-1]["Volume"], 60.0)
        self.assertEqual(result.iloc[-1]["Amount"], 1270.0)
        self.assertTrue(result.attrs["includes_intraday_daily_bar"])
        self.assertEqual(result.attrs["symbol_name"], "C长鑫")

class MarketSnapshotTests(unittest.TestCase):
    def test_batch_request_never_degrades_to_per_stock_requests(self):
        rows = flatten_a_share_universe(A_SHARE_UNIVERSE)
        fake_session = _MarketRowsSession()
        with patch("market_snapshot.requests.Session", return_value=fake_session):
            result = _request_market_rows(rows)
        self.assertEqual(len(result), 88)
        self.assertEqual(len(fake_session.calls), 3)
        self.assertTrue(all(len(call) <= 43 for call in fake_session.calls))

    def test_rankings_sort_and_place_invalid_pe_last(self):
        frame = pd.DataFrame(
            [
                {"name": "甲", "change_pct": 1, "amount": 20, "market_cap": 30, "pe_ttm": 15},
                {"name": "乙", "change_pct": 3, "amount": 10, "market_cap": 50, "pe_ttm": 8},
                {"name": "丙", "change_pct": np.nan, "amount": 30, "market_cap": 40, "pe_ttm": -2},
            ]
        )
        self.assertEqual(rank_snapshot(frame, "change_pct").iloc[0]["name"], "乙")
        self.assertEqual(rank_snapshot(frame, "amount").iloc[0]["name"], "丙")
        self.assertEqual(rank_snapshot(frame, "market_cap").iloc[0]["name"], "乙")
        pe_rank = rank_snapshot(frame, "pe_ttm")
        self.assertEqual(pe_rank.iloc[0]["name"], "乙")
        self.assertEqual(pe_rank.iloc[-1]["name"], "丙")
