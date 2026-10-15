import unittest
import tempfile
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from datetime import date
from browser_state import valid_preferences

from financial_rankings import _annual_comparison_row
from formatters import format_statistics
from new_listing import get_new_listing_state
from watchlist import summarize_watchlist, add_watchlist_item, load_watchlist, save_watchlist


class BrowserPreferencesTests(unittest.TestCase):
    def test_restores_dates_and_ignores_invalid_or_unrelated_values(self):
        result = valid_preferences({
            "display_start": "2026-08-01", "display_end": "invalid",
            "page_navigation": "股票池排行", "rsi_period": 999,
            "ma_periods": [5, 10, 5], "show_bbi": True,
            "access_token": "must not be restored",
        })
        self.assertEqual(result, {
            "display_start": date(2026, 8, 1), "ma_periods": [5, 10], "show_bbi": True,
        })


class WatchlistTests(unittest.TestCase):
    def test_intraday_values_use_today_and_compress_lunch(self):
        from watchlist import intraday_values
        curve = pd.DataFrame({"Price": [999., 10., 11., 999., 12.]},
            index=pd.to_datetime(["2026-10-13 15:00", "2026-10-14 09:30", "2026-10-14 11:30", "2026-10-14 12:00", "2026-10-14 15:00"]))
        values = intraday_values(curve, date(2026, 10, 14), 10.)
        self.assertEqual(len(values), 3)
        self.assertEqual(values[0], 0.)
        self.assertAlmostEqual(values[1], 10.)
        self.assertAlmostEqual(values[2], 20.)
        self.assertEqual(intraday_values(curve, date(2026, 10, 15), 10.), [])

    def test_delete_undo_preserves_concurrent_additions_and_pin_metadata(self):
        from watchlist import delete_watchlist_items, restore_watchlist_items, load_watchlist_preferences, save_watchlist_preferences
        items = [{"ticker": "000001.SZ", "name": "银行", "pinned": True, "tag": "金融"}, {"ticker": "600519.SH", "name": "白酒"}]
        remaining, removed = delete_watchlist_items(items, {"000001.SZ"})
        added = {"ticker": "300308.SZ", "name": "光模块"}
        self.assertEqual(restore_watchlist_items([*remaining, added], removed), [*items, added])
        self.assertEqual(restore_watchlist_items(items, removed), items)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "view.json"
            save_watchlist_preferences("最近加入优先", ["name", "turnover", "not-a-field"], path)
            prefs = load_watchlist_preferences(path)
            self.assertEqual(prefs["sort"], "最近加入优先")
            self.assertIn("turnover", prefs["columns"])
            self.assertNotIn("not-a-field", prefs["columns"])
            saved = Path(folder) / "watchlist.json"
            save_watchlist(items, saved)
            self.assertEqual(load_watchlist(saved), items)

    def test_native_watchlist_reuses_quotes_handles_failure_and_compact_columns(self):
        from streamlit.testing.v1 import AppTest
        from data_fetcher import DataFetchError
        from market_snapshot import MarketSnapshotError
        today = str(pd.Timestamp.now(tz="Asia/Shanghai").date())
        items = [{"ticker": "000001.SZ", "name": "银行"}, {"ticker": "300308.SZ", "name": "光模块"}]
        quotes = pd.DataFrame(items).assign(industry="测试", price=[10., 11.], previous_close=10., change_pct=[0., 10.],
            amount=1e8, market_cap=1e10, quote_time=f"{today} 10:00", trade_date=today, stale=False)
        curve = pd.DataFrame({"Price": [10., 11.]}, index=pd.to_datetime([f"{today} 09:30", f"{today} 10:30"]))
        with patch("watchlist.load_watchlist", return_value=items), patch("watchlist.load_watchlist_snapshot", return_value=quotes) as snapshot, \
             patch("watchlist.load_intraday", return_value=curve) as intraday, patch("watchlist.save_browser_state"), \
             patch("watchlist.save_watchlist_preferences"), patch("watchlist.load_watchlist_benchmark", return_value={"date": today, "change_pct": 2.}), \
             patch("watchlist.load_watchlist_preferences", return_value={"sort": "涨幅优先", "columns": ["name", "ticker", "price", "change_pct", "intraday", "amount"], "native_sort": None}), \
             patch("watchlist.load_watchlist_status", return_value={"statuses": {}}), \
             patch("watchlist.a_share_session_state", return_value={"trading": False, "calendar_ok": True, "label": "13:00 开盘"}):
            app = AppTest.from_string("from watchlist import render_watchlist_overview\nrender_watchlist_overview({})")
            app.run(timeout=15)
            self.assertFalse(app.exception)
            grid = next(table for table in app.dataframe if table.key.startswith("watchlist-grid:"))
            self.assertEqual(grid.value.iloc[0]["ticker"], "300308.SZ")
            self.assertEqual(intraday.call_count, 2)
            self.assertIn("+3.00", app.metric[1].delta)
            self.assertEqual(app.selectbox(key="watchlist_lookup").value, None)
            app.run(timeout=15)
            snapshot.assert_called_once()
            self.assertEqual(intraday.call_count, 2)
            snapshot.side_effect = MarketSnapshotError("offline")
            app.button(key="watchlist_refresh").click().run(timeout=15)
            self.assertFalse(app.exception)
            grid = next(table for table in app.dataframe if table.key.startswith("watchlist-grid:"))
            self.assertEqual(len(grid.value), 2)
            self.assertTrue(app.warning)
            self.assertIn("缓存数据", grid.value["note"].tolist())
            app.session_state["_viewport_width"] = 390
            app.run(timeout=15)
            grid = next(table for table in app.dataframe if table.key.startswith("watchlist-grid:"))
            config = __import__("json").loads(grid.proto.columns)
            self.assertTrue(config["intraday"]["hidden"])
            self.assertTrue(config["amount"]["hidden"])

    def test_native_sort_and_suspend_state_are_persisted_and_numeric(self):
        from watchlist import build_watchlist_table, load_watchlist_preferences, save_watchlist_preferences
        items = [{"ticker": "000001.SZ", "name": "银行"}, {"ticker": "300308.SZ", "name": "光模块", "pinned": True}]
        snapshot = pd.DataFrame(items).assign(industry="测试", price=[10., 20.], previous_close=[10., 18.],
            change_pct=[0., 11.], amount=1e8, quote_time="2026-10-14 10:00", trade_date="2026-10-14", stale=False, suspended=[True, False])
        native = {"field": "price", "ascending": True}
        table = build_watchlist_table(snapshot, items, {}, {"300308.SZ": {"base_5": 10., "base_20": 8.}},
            pd.Timestamp("2026-10-14 10:00", tz="Asia/Shanghai"), True, native_sort=native)
        self.assertEqual(table.iloc[0]["ticker"], "300308.SZ")
        self.assertEqual(table.iloc[0]["return_5"], 100.)
        self.assertEqual(table.iloc[0]["return_20"], 150.)
        self.assertEqual(table.loc[table["ticker"].eq("000001.SZ"), "note"].iloc[0], "停牌")
        self.assertEqual(summarize_watchlist(snapshot)["count"], 1)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "view.json"
            save_watchlist_preferences("涨幅优先", ["name", "price"], path, native_sort=native)
            self.assertEqual(load_watchlist_preferences(path)["native_sort"], native)
    def test_summary_excludes_cache_old_dates_and_missing_changes(self):
        frame = pd.DataFrame({
            "ticker": ["a", "b", "c", "d", "e", "f"], "name": ["A", "B", "C", "D", "E", "F"],
            "trade_date": ["2026-09-30"] * 5 + ["2026-09-29"],
            "change_pct": [3., -1., 0., 90., float("nan"), 80.],
            "stale": [False, False, False, True, False, False],
        })
        summary = summarize_watchlist(frame)
        self.assertEqual(summary["count"], 3)
        self.assertAlmostEqual(summary["average"], 2 / 3)
        self.assertEqual((summary["up"], summary["down"], summary["flat"]), (1, 1, 1))
        self.assertEqual(summary["leader"]["ticker"], "a")
        self.assertEqual(summary["laggard"]["ticker"], "b")
        frame["stale"] = True
        self.assertIsNone(summarize_watchlist(frame)["average"])
        self.assertEqual(summarize_watchlist(frame)["count"], 0)
        self.assertEqual(summarize_watchlist(frame.iloc[:1].assign(stale=False))["average"], 3.)
        self.assertIsNone(summarize_watchlist(frame.iloc[:0])["date"])

    def test_favorites_keep_unknown_codes_and_reject_duplicates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "watchlist.json"
            items = add_watchlist_item([], "688525")
            save_watchlist(items, path)
            self.assertEqual(load_watchlist(path), [{"ticker": "688525.SH", "name": ""}])
            with self.assertRaises(ValueError):
                add_watchlist_item(items, "sh688525")
            save_watchlist([], path)
            self.assertEqual(load_watchlist(path), [])

    def test_snapshot_cache_retains_unrequested_tickers_and_fills_names(self):
        from market_snapshot import _save_snapshot_cache, _load_snapshot_cache, _merge_snapshot_rows
        with tempfile.TemporaryDirectory() as folder, patch("market_snapshot.CACHE_PATH", Path(folder) / "quotes.csv"):
            _save_snapshot_cache(pd.DataFrame([{"ticker": "000001.SZ", "price": 10}, {"ticker": "688525.SH", "price": 20}]))
            _save_snapshot_cache(pd.DataFrame([{"ticker": "688525.SH", "price": 21}]))
            cached = _load_snapshot_cache().set_index("ticker")
            self.assertEqual(cached.loc["000001.SZ", "price"], 10)
            self.assertEqual(cached.loc["688525.SH", "price"], 21)
            frame = _merge_snapshot_rows([{"ticker": "688525.SH", "name": "", "industry": "未分类"}],
                {"688525": {"provider_name": "佰维存储", "price": 21}}, {})
            self.assertEqual(frame.iloc[0]["name"], "佰维存储")

    def test_closed_delayed_cached_and_missing_quotes_are_distinct(self):
        from watchlist import _quote_status
        row = SimpleNamespace(price=32.47, stale=False, trade_date="2026-10-09", quote_time="2026-10-09 16:00:56")
        saturday = pd.Timestamp("2026-10-10 11:00", tz="Asia/Shanghai")
        self.assertEqual(_quote_status(row, "2026-10-09", saturday, False), "")
        monday = pd.Timestamp("2026-10-12 10:00", tz="Asia/Shanghai")
        self.assertEqual(_quote_status(row, "2026-10-09", monday, True), "数据延迟")
        row.stale = True
        self.assertEqual(_quote_status(row, "2026-10-09", saturday, False), "缓存数据")
        row.price = float("nan")
        self.assertEqual(_quote_status(row, "2026-10-09", saturday, False), "数据缺失")

    def test_quote_format_keeps_missing_values_and_neutral_zero(self):
        from watchlist import _quote_number, _change_color
        self.assertEqual(_quote_number(None), "—")
        self.assertEqual(_quote_number(0, signed=True, suffix="%"), "0.00%")
        self.assertEqual(_quote_number(.14, signed=True), "+0.14")
        self.assertEqual(_quote_number(-1.09, signed=True), "-1.09")
        self.assertEqual(_change_color(pd.NA), "watch-flat")


class NewListingTests(unittest.TestCase):
    def test_first_day_listing_uses_safe_guards(self):
        state = get_new_listing_state(pd.DataFrame({"Close": [49.0]}), rsi_period=14)

        self.assertEqual(state["daily_bars"], 1)
        self.assertIsNone(state["previous_close"])
        self.assertFalse(state["show_rows_slider"])
        self.assertFalse(state["trend_ready"])
        self.assertFalse(state["rsi_ready"])
        self.assertFalse(state["macd_ready"])
        self.assertFalse(state["volatility_ready"])

class FormatterTests(unittest.TestCase):
    def test_statistics_summary_is_localized_and_compact(self):
        summary = format_statistics(
            pd.DataFrame(
                {
                    "Open": [10, 20],
                    "Volume": [10_000, 20_000],
                    "Amount": [100_000_000, 200_000_000],
                }
            ),
            "CN",
        )

        self.assertEqual(summary.index.tolist()[0], "平均值")
        self.assertNotIn("数量", summary.index)
        self.assertIn("开盘价", summary.columns)
        self.assertEqual(summary.loc["平均值", "成交量"], "1.50万股")
        self.assertEqual(summary.loc["平均值", "成交额"], "1.50亿元")


class PeerComparisonTests(unittest.TestCase):
    def test_uses_latest_annual_report_and_calculates_margin(self):
        reports = pd.DataFrame(
            [
                {"报告期": "2023-12-31", "报告类型": "年报", "营业总收入": "100亿", "净利润": "10亿"},
                {"报告期": "2024-09-30", "报告类型": "三季报", "营业总收入": "90亿", "净利润": "12亿"},
                {"报告期": "2024-12-31", "报告类型": "年报", "营业总收入": "200亿", "净利润": "30亿", "资产负债率": "42.5%"},
            ]
        )

        row = _annual_comparison_row(
            {"name": "示例公司", "ticker": "000001.SZ"}, reports, 2_000_000_000
        )

        self.assertEqual(row["报告期"], "2024-12-31")
        self.assertEqual(row["营收"], 20_000_000_000)
        self.assertEqual(row["净利润"], 3_000_000_000)
        self.assertEqual(row["产品表现代理"], 15.0)
        self.assertEqual(row["资产负债率"], 42.5)
        self.assertEqual(row["投资支出"], 2_000_000_000)
        self.assertEqual(row["投资支出占营收"], 10.0)
