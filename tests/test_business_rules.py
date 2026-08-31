import unittest

import pandas as pd

from financial_rankings import _annual_comparison_row
from formatters import format_statistics
from new_listing import get_new_listing_state


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
