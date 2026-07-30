import unittest

import pandas as pd

from data_fetcher import _parse_yahoo_financial_timeseries
from formatters import format_financial_report_table


class YahooFinancialReportTests(unittest.TestCase):
    def test_parses_annual_and_quarterly_reports_in_a_shared_schema(self):
        payload = {
            "timeseries": {"result": [
                {"meta": {"type": ["annualTotalRevenue"]}, "annualTotalRevenue": [{"asOfDate": "2025-12-31", "reportedValue": {"raw": 100_000_000_000}}]},
                {"meta": {"type": ["annualNetIncome"]}, "annualNetIncome": [{"asOfDate": "2025-12-31", "reportedValue": {"raw": 25_000_000_000}}]},
                {"meta": {"type": ["quarterlyTotalRevenue"]}, "quarterlyTotalRevenue": [{"asOfDate": "2026-03-31", "reportedValue": {"raw": 120_000_000_000}}]},
                {"meta": {"type": ["quarterlyBasicEPS"]}, "quarterlyBasicEPS": [{"asOfDate": "2026-03-31", "reportedValue": {"raw": 1.5}}]},
            ]}
        }
        reports = _parse_yahoo_financial_timeseries(payload)

        self.assertEqual(reports["报告类型"].tolist(), ["季报", "年报"])
        self.assertEqual(reports.loc[1, "净利润"], 25_000_000_000)
        self.assertEqual(reports.loc[0, "基本每股收益"], 1.5)

    def test_formats_us_and_korean_amounts_with_readable_units(self):
        frame = pd.DataFrame({"营业总收入": [100_000_000_000], "基本每股收益": [1.5]})

        self.assertEqual(format_financial_report_table(frame, "US").loc[0, "营业总收入"], "100.00B美元")
        self.assertEqual(format_financial_report_table(frame, "KR").loc[0, "基本每股收益"], "1.50")

    def test_can_display_korean_financial_amounts_in_us_dollars(self):
        frame = pd.DataFrame({"营业总收入": [1_400_000_000_000], "基本每股收益": [1400]})
        formatted = format_financial_report_table(frame, "US", currency_multiplier=1 / 1400)

        self.assertEqual(formatted.loc[0, "营业总收入"], "1.00B美元")
        self.assertEqual(formatted.loc[0, "基本每股收益（美元）"], "1.00")


if __name__ == "__main__":
    unittest.main()
