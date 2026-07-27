import unittest

import pandas as pd

from formatters import chart_unit, format_amount, format_statistics, format_volume


class FormatterTests(unittest.TestCase):
    def test_china_share_volume_uses_wan_and_yi_units(self):
        self.assertEqual(format_volume(27_678_291, "CN"), "2767.83万股")
        self.assertEqual(format_volume(123_000_000, "CN"), "1.23亿股")

    def test_china_amount_uses_wan_and_yi_units(self):
        self.assertEqual(format_amount(34_960_564_000, "CN"), "349.61亿元")
        self.assertEqual(format_amount(12_345, "CN"), "1.23万元")

    def test_chart_units_match_market_conventions(self):
        self.assertEqual(chart_unit("volume", "CN"), (1e4, "万股"))
        self.assertEqual(chart_unit("amount", "CN"), (1e8, "亿元"))
        self.assertEqual(chart_unit("amount", "US"), (1e6, "百万美元"))

    def test_statistics_summary_is_localized_and_compact(self):
        summary = format_statistics(
            pd.DataFrame({"Open": [10, 20], "Volume": [10_000, 20_000], "Amount": [100_000_000, 200_000_000]}),
            "CN",
        )

        self.assertEqual(summary.index.tolist()[0], "数量")
        self.assertIn("开盘价", summary.columns)
        self.assertEqual(summary.loc["平均值", "成交量"], "1.50万股")
        self.assertEqual(summary.loc["平均值", "成交额"], "1.50亿元")


if __name__ == "__main__":
    unittest.main()
