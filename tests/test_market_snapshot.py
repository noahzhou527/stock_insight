import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from a_share_universe import A_SHARE_UNIVERSE
from market_snapshot import (
    _adjust_valuation_to_close,
    _latest_completed_close,
    _request_market_rows,
    flatten_a_share_universe,
    rank_snapshot,
)


class _FakeResponse:
    def __init__(self, diff):
        self._diff = diff

    def raise_for_status(self):
        return None

    def json(self):
        return {"rc": 0, "data": {"diff": self._diff}}


class _FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, _url, params, **_kwargs):
        secids = params["secids"].split(",")
        self.calls.append(secids)
        return _FakeResponse([{"f12": secid.split(".")[1]} for secid in secids])


class _FlakySession(_FakeSession):
    def get(self, _url, params, **_kwargs):
        if not self.calls:
            self.calls.append(params["secids"].split(","))
            raise ConnectionError("transient disconnect")
        return super().get(_url, params, **_kwargs)


class MarketSnapshotTests(unittest.TestCase):
    def test_universe_is_complete_and_uses_current_beijing_codes(self):
        rows = flatten_a_share_universe(A_SHARE_UNIVERSE)
        tickers = {row["ticker"] for row in rows}
        self.assertEqual(len(rows), 86)
        self.assertEqual(len(tickers), 86)
        self.assertIn("920190.BJ", tickers)
        self.assertIn("920725.BJ", tickers)

    def test_batch_request_never_degrades_to_per_stock_requests(self):
        rows = flatten_a_share_universe(A_SHARE_UNIVERSE)
        fake_session = _FakeSession()
        with patch("market_snapshot.requests.Session", return_value=fake_session):
            result = _request_market_rows(rows)
        self.assertEqual(len(result), 86)
        self.assertEqual(len(fake_session.calls), 2)
        self.assertTrue(all(len(call) == 43 for call in fake_session.calls))

    def test_batch_retries_a_transient_disconnect(self):
        rows = flatten_a_share_universe(A_SHARE_UNIVERSE)
        flaky_session = _FlakySession()
        with patch("market_snapshot.requests.Session", return_value=flaky_session):
            result = _request_market_rows(rows)
        self.assertEqual(len(result), 86)
        self.assertEqual(len(flaky_session.calls), 3)

    def test_latest_completed_daily_close_and_valuation_scaling(self):
        tz = ZoneInfo("Asia/Shanghai")
        before_close = datetime(2026, 7, 10, 10, 30, tzinfo=tz)
        after_close = datetime(2026, 7, 10, 15, 30, tzinfo=tz)
        self.assertEqual(
            _latest_completed_close(110, 100, "2026-07-10", before_close), 100
        )
        self.assertEqual(
            _latest_completed_close(110, 100, "2026-07-10", after_close), 110
        )
        self.assertEqual(_adjust_valuation_to_close(220, 110, 100), 200)

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


if __name__ == "__main__":
    unittest.main()
