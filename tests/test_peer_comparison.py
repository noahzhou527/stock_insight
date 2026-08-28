import unittest

import pandas as pd

from financial_rankings import _annual_comparison_row


class PeerComparisonTest(unittest.TestCase):
    def test_uses_latest_annual_report_and_calculates_margin(self):
        reports = pd.DataFrame(
            [
                {"报告期": "2023-12-31", "报告类型": "年报", "营业总收入": "100亿", "净利润": "10亿"},
                {"报告期": "2024-09-30", "报告类型": "三季报", "营业总收入": "90亿", "净利润": "12亿"},
                {"报告期": "2024-12-31", "报告类型": "年报", "营业总收入": "200亿", "净利润": "30亿"},
            ]
        )

        row = _annual_comparison_row({"name": "示例公司", "ticker": "000001.SZ"}, reports)

        self.assertEqual(row["报告期"], "2024-12-31")
        self.assertEqual(row["营收"], 20_000_000_000)
        self.assertEqual(row["净利润"], 3_000_000_000)
        self.assertEqual(row["产品表现代理"], 15.0)


if __name__ == "__main__":
    unittest.main()
