"""Offline watchlist calendar and supplemental-field contracts."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from data_fetcher import DataFetchError
from services import market_data as market
from services import watchlist_data as extra


class WatchlistDataTests(unittest.TestCase):
    def test_official_trade_status_is_not_inferred_from_missing_prices(self):
        extra.load_watchlist_status.clear()
        tables = {"600105.SH": {"table": {"tradeStatus": ["交易"]}}, "300308.SZ": {"table": {"tradeStatus": ["停牌"]}}}
        with patch.object(extra, "quotes", return_value=tables) as quotes:
            result = extra.load_watchlist_status(("600105.SH", "300308.SZ"))
            self.assertEqual(result["statuses"]["300308.SZ"], "停牌")
            quotes.assert_called_once_with(("600105.SH", "300308.SZ"), "tradeStatus")
        extra.load_watchlist_status.clear()

    def test_holiday_lunch_and_session_boundaries_use_official_calendar(self):
        dates = pd.DatetimeIndex(["2026-10-09", "2026-10-12"])
        with patch.object(market, "load_a_share_trade_dates", return_value=dates):
            self.assertFalse(market.a_share_session_state("2026-10-01 10:00")["trading"])
            self.assertFalse(market.a_share_session_state("2026-10-10 10:00")["trading"])
            for time, expected in [("09:29:59", False), ("09:30:00", True), ("11:29:59", True), ("11:30:00", False), ("12:00:00", False), ("13:00:00", True), ("14:59:59", True), ("15:00:00", False)]:
                self.assertEqual(market.a_share_session_state("2026-10-12 " + time)["trading"], expected)
            self.assertEqual(market.a_share_session_state("2026-10-12 12:00")["label"], "13:00 开盘")
        with patch.object(market, "load_a_share_trade_dates", side_effect=DataFetchError("ifind_calendar", "offline")):
            self.assertFalse(market.a_share_session_state("2026-10-12 10:00")["trading"])
            self.assertFalse(market.a_share_session_state("2026-10-12 10:00")["calendar_ok"])

    def test_calendar_survives_memory_reset_and_retains_verified_copy_on_failure(self):
        market.load_a_share_trade_dates.clear()
        with tempfile.TemporaryDirectory() as folder, patch.object(market, "_cache_path", return_value=Path(folder) / "calendar.json"), \
             patch.object(market, "calendar", return_value=pd.DatetimeIndex(["2026-10-12"])) as fetch:
            self.assertEqual(len(market.load_a_share_trade_dates(2026)), 1)
            market.load_a_share_trade_dates.clear()
            self.assertEqual(len(market.load_a_share_trade_dates(2026)), 1)
            fetch.assert_called_once()
        market.load_a_share_trade_dates.clear()

    def test_optional_fields_and_return_bases_do_not_estimate_missing_data(self):
        extra.load_watchlist_extras.clear()
        table = {"600105.SH": {"time": ["2026-10-14 10:00"], "table": {"open": [10.], "high": [12.], "low": [9.], "preClose": [10.], "turnoverRatio": [2.]}}}
        history = pd.DataFrame({"Close": range(10, 32)}, index=pd.bdate_range(end="2026-10-14", periods=22))
        with patch.object(extra, "quotes", return_value=table) as quotes, patch.object(extra, "historical", return_value=history):
            fields = ("amplitude", "turnover", "return_5", "return_20")
            result = extra.load_watchlist_extras(("600105.SH",), "2026-10-14", fields)["600105.SH"]
            self.assertEqual(result["amplitude"], 30.)
            self.assertEqual(result["turnover"], 2.)
            self.assertEqual(result["base_5"], 26.)
            self.assertEqual(result["base_20"], 11.)
            extra.load_watchlist_extras(("600105.SH",), "2026-10-14", fields)
            quotes.assert_called_once()
        extra.load_watchlist_extras.clear()
        with patch.object(extra, "quotes", side_effect=DataFetchError("ifind_permission", "No permission")):
            result = extra.load_watchlist_extras(("600105.SH",), "2026-10-14", ("turnover",))["600105.SH"]
            self.assertIn("不可用", result["note"])
            self.assertNotIn("turnover", result)
        extra.load_watchlist_extras.clear()


if __name__ == "__main__":
    unittest.main()
