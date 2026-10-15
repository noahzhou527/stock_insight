"""Focused offline checks for iFinD isolation, normalization and caching."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

import ifind_data as provider
from data_fetcher import DataFetchError
from market_snapshot import fetch_a_share_market_snapshot


class IFinDTests(unittest.TestCase):
    def test_security_list_survives_memory_cache_reset_and_refreshes_next_day(self):
        today = pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y%m%d")
        result = {"tables": [{"table": {"p03291_f002": ["600519.SH"]}}]}
        quote = {"600519.SH": {"table": {"latest": [11], "preClose": [10]}}}
        with tempfile.TemporaryDirectory() as folder, patch.object(provider, "CACHE_DIR", Path(folder)), \
             patch.object(provider, "request", return_value=result) as request, patch.object(provider, "quotes", return_value=quote):
            provider.market_breadth()
            request.assert_called_once()
            provider._REQUEST_CACHE.clear()
            provider._cache_path("breadth", "CN").unlink()
            provider.market_breadth()
            self.assertEqual(request.call_count, 1)
            provider._cache_path("breadth", "CN").unlink()
            provider._write_frame(provider._cache_path("universe", "CN"), pd.DataFrame({"code": ["600519.SH"]}), date="20000101")
            provider.market_breadth()
            self.assertEqual(request.call_count, 2)
            _, meta = provider._read_frame(provider._cache_path("universe", "CN"))
            self.assertEqual(meta["date"], today)
            provider._cache_path("breadth", "CN").unlink()
            provider._write_frame(provider._cache_path("universe", "CN"), pd.DataFrame({"code": ["invalid"]}), date=today)
            provider.market_breadth()
            self.assertEqual(request.call_count, 3)

    def test_financial_cache_does_not_add_an_index_column(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "financial.json"
            frame = pd.DataFrame([{"报告期": "2026-06-30", "净利润": 100.0}])
            provider._write_frame(path, frame)
            loaded, _ = provider._read_frame(path)
            self.assertEqual(list(loaded.columns), list(frame.columns))

    def test_permission_failure_never_uses_public_provider(self):
        with patch.object(provider, "_session") as session:
            session.return_value.post.return_value.json.return_value = {
                "errorcode": -4230, "errmsg": "No permission for this market"
            }
            with self.assertRaises(DataFetchError) as failure:
                provider._post("real_time_quotation", {"codes": "AAPL.O"}, {"access_token": "secret"})
            self.assertEqual(failure.exception.category, "ifind_permission")
            self.assertEqual(session.return_value.post.call_args.args[0], provider.API_ROOT + "real_time_quotation")
            self.assertNotIn("secret", str(failure.exception))

    def test_malformed_columns_are_rejected(self):
        with self.assertRaises(DataFetchError):
            provider._table_frame({"time": ["2026-10-08", "2026-10-09"], "table": {"close": [1]}})

    def test_index_does_not_plot_basket_vwap_as_index_points(self):
        from services import market_overview_data as overview
        daily = pd.DataFrame({"Close": [100.0, 101.0], "Amount": [1000.0, 2000.0]}, index=pd.to_datetime(["2026-10-08", "2026-10-09"]))
        minute = pd.DataFrame({"Price": [101.0], "AvgPrice": [10000.0]}, index=pd.to_datetime(["2026-10-09 10:00"]))
        with patch.object(overview, "historical", return_value=daily), patch.object(overview, "quotes", return_value={}), patch.object(overview, "intraday", return_value=minute):
            result = overview.fetch_cn_index({"name": "上证指数", "symbol": "1A0001"})
            self.assertNotIn("AvgPrice", result["intraday"])

    def test_refresh_token_uses_current_token_without_rotating_other_sessions(self):
        provider._TOKEN_CACHE.clear()
        with patch.object(provider, "_setting", side_effect=lambda key: "refresh" if key == "THS_REFRESH_TOKEN" else None), patch.object(provider, "_post", return_value={"data": {"access_token": "access"}}) as post:
            self.assertEqual(provider.access_token(), "access")
            self.assertEqual(provider.access_token(), "access")
            post.assert_called_once_with("get_access_token", {}, {"refresh_token": "refresh"})
        provider._TOKEN_CACHE.clear()

    def test_daily_cache_is_incremental_and_does_not_estimate_amount(self):
        def result(payload):
            return {"tables": [{"thscode": "600519.SH", "time": ["2026-10-08", "2026-10-09"], "table": {
                "open": [10, 11], "high": [12, 13], "low": [9, 10], "close": [11, 12], "volume": [100, 200], "amount": [None, 2350]
            }}]}
        with tempfile.TemporaryDirectory() as folder, patch.object(provider, "CACHE_DIR", Path(folder)), patch.object(provider, "request", side_effect=lambda endpoint, payload, **kwargs: result(payload)) as request:
            first = provider.historical("600519.SH", "2026-10-01", "2026-10-09")
            self.assertTrue(pd.isna(first.iloc[0]["Amount"]))
            self.assertEqual(first.iloc[1]["Amount"], 2350)
            provider.historical("600519.SH", "2026-10-01", "2026-10-09")
            self.assertEqual(request.call_count, 1)
            provider.historical("600519.SH", "2026-10-01", "2026-10-10")
            self.assertEqual(request.call_args.args[1]["startdate"], "2026-10-06")
            self.assertEqual(request.call_args.args[1]["functionpara"]["CPS"], "1")

    def test_snapshot_fallback_uses_only_isolated_ifind_cache(self):
        rows = [{"name": "测试", "ticker": "600519.SH", "industry": "测试"}]
        with tempfile.TemporaryDirectory() as folder, patch("market_snapshot.CACHE_PATH", Path(folder) / "ifind.csv"), patch.object(provider, "snapshot", side_effect=DataFetchError("ifind_permission", "No permission")):
            with self.assertRaisesRegex(RuntimeError, "No permission"):
                fetch_a_share_market_snapshot(rows)

    def test_overseas_symbols_do_not_guess_exchange(self):
        with patch.object(provider, "_setting", return_value=None):
            self.assertEqual(provider.code_for("AAPL", "US"), "AAPL.O")
            with self.assertRaises(DataFetchError):
                provider.code_for("UNKNOWN", "US")
            with self.assertRaises(DataFetchError):
                provider.code_for("005930.KS", "KR")


if __name__ == "__main__":
    unittest.main()
