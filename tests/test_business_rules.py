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
    def test_date_defaults_reset_legacy_values_and_remember_manual_edits(self):
        from datetime import datetime
        from calendar import monthrange
        from zoneinfo import ZoneInfo
        from streamlit.testing.v1 import AppTest
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        year_ago = today.replace(year=today.year - 1,
            day=min(today.day, monthrange(today.year - 1, today.month)[1]))
        source = "from sidebar import render_sidebar\nrender_sidebar('US', {})"
        app = AppTest.from_string(source)
        app.session_state["display_start"] = date(2025, 9, 18)
        app.session_state["display_end"] = date(2026, 9, 18)
        app.run(timeout=15)
        self.assertFalse(app.exception)
        self.assertEqual(app.date_input(key="display_start").value, year_ago)
        self.assertEqual(app.date_input(key="display_end").value, today)
        app.date_input(key="display_end").set_value(date(2026, 9, 18)).run(timeout=15)
        self.assertEqual(app.date_input(key="display_start").value, year_ago)
        app.date_input(key="display_start").set_value(date(2025, 8, 1)).run(timeout=15)
        saved = valid_preferences({"display_start": "2025-08-01", "display_end": "2026-09-18",
            "display_start_manual": app.session_state["display_start_manual"],
            "display_end_manual": app.session_state["display_end_manual"]})
        reopened = AppTest.from_string(source)
        for key, value in saved.items():
            reopened.session_state[key] = value
        reopened.run(timeout=15)
        self.assertFalse(reopened.exception)
        self.assertEqual(reopened.date_input(key="display_start").value, date(2025, 8, 1))
        self.assertEqual(reopened.date_input(key="display_end").value, date(2026, 9, 18))
        self.assertFalse(reopened.date_input(key="display_end").disabled)

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

    def test_overview_route_and_round_trip_keep_stock_and_preferences(self):
        from streamlit.testing.v1 import AppTest
        from data_fetcher import DataFetchError
        items = [{"ticker": "688525.SH", "name": "佰维存储"}, {"ticker": "000001.SZ", "name": "平安银行"}]
        quotes = pd.DataFrame(items).assign(industry="未分类", price=[20., 10.], previous_close=[19., 11.],
            change_pct=[5., -9.], amount=1e8, quote_time="2026-09-30 15:00:00", trade_date="2026-09-30", stale=False)
        with patch("watchlist.load_watchlist", return_value=items) as favorites, patch("watchlist.load_watchlist_snapshot", return_value=quotes) as batch, \
             patch("browser_state._storage", return_value=SimpleNamespace(loaded={})), \
             patch("watchlist.is_a_share_trading_session", return_value=False) as trading, \
             patch("services.market_data.load_data", side_effect=DataFetchError("unavailable", "模拟不可用")) as daily:
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
            for key, value in {"_browser_state_ready": True, "market_navigation": "A股", "market_view_navigation": "我的自选",
                "watchlist_search": "银行", "watchlist_sort": "涨幅优先", "display_start": date(2026, 1, 1), "show_bbi": True}.items():
                app.session_state[key] = value
            app.run(timeout=15)
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value, "2")
            daily.assert_not_called()
            batch.assert_called_once()
            app.button(key="watch-open:000001.SZ").click().run(timeout=15)
            self.assertFalse(app.exception)
            self.assertEqual(app.sidebar.selectbox(key="a_share_watchlist_ticker").value, "000001.SZ")
            self.assertEqual(daily.call_args.args[0], "000001.SZ")
            next(button for button in app.button if button.label == "← 返回自选池总览").click().run(timeout=15)
            self.assertFalse(app.exception)
            self.assertEqual(app.text_input(key="watchlist_search").value, "银行")
            self.assertEqual(app.selectbox(key="watchlist_sort").value, "涨幅优先")
            self.assertEqual(app.session_state["display_start"], date(2026, 1, 1))
            self.assertTrue(app.session_state["show_bbi"])
            self.assertEqual(batch.call_count, 2)
            trading.return_value = True
            app.run(timeout=15)
            self.assertEqual(batch.call_count, 3)
            trading.return_value = False
            from market_snapshot import MarketSnapshotError
            batch.side_effect = MarketSnapshotError("offline")
            app.button(key="watchlist_refresh").click().run(timeout=15)
            self.assertFalse(app.exception)
            self.assertEqual(app.metric[1].value, "—")
            self.assertEqual(app.metric[3].value, "0 / 2")
            self.assertTrue(app.warning)
            favorites.return_value = []
            app.run(timeout=15)
            self.assertFalse(app.exception)
            self.assertEqual(batch.call_count, 4)
            batch.side_effect = None
            with patch("watchlist.save_watchlist", side_effect=lambda values: setattr(favorites, "return_value", values)):
                app.text_input(key="manual_watchlist_ticker").set_value("000001")
                next(button for button in app.button if button.label == "加入自选股").click().run(timeout=15)
                self.assertEqual(favorites.return_value[0]["ticker"], "000001.SZ")
                self.assertEqual(app.session_state["watchlist_view"], "总览")
                app.text_input(key="manual_watchlist_ticker").set_value("000001")
                next(button for button in app.button if button.label == "加入自选股").click().run(timeout=15)
                self.assertTrue(app.error)
                self.assertEqual(len(favorites.return_value), 1)
                app.button(key="watch-open:000001.SZ").click().run(timeout=15)
                next(button for button in app.sidebar.button if button.label == "移出自选股").click().run(timeout=15)
                self.assertFalse(app.exception)
                self.assertEqual(favorites.return_value, [])
                self.assertEqual(app.session_state["watchlist_view"], "总览")


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
