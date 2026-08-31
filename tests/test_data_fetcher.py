import unittest
from unittest.mock import patch

import pandas as pd

from data_fetcher import (
    _covers_requested_range,
    _calculate_ttm_net_profit,
    _latest_annual_cash_flow_value,
    _parse_yahoo_financial_timeseries,
    fetch_a_share_data,
    fetch_yahoo_intraday,
)


class _FakeTicker:
    def __init__(self, _ticker, session=None):
        self.session = session

    def history(self, *, period, interval, **_kwargs):
        if interval == "5m":
            index = pd.to_datetime(
                [
                    "2026-07-21 13:30:00+00:00",
                    "2026-07-22 13:30:00+00:00",
                    "2026-07-22 13:35:00+00:00",
                ]
            )
            return pd.DataFrame(
                {
                    "Open": [99, 100, 101],
                    "High": [100, 101, 102],
                    "Low": [98, 99, 100],
                    "Close": [99.5, 100.5, 101.5],
                    "Volume": [10, 20, 30],
                },
                index=index,
            )
        return pd.DataFrame(
            {"Close": [98.0, 100.0]},
            index=pd.to_datetime(["2026-07-21", "2026-07-22"]),
        )


class AShareDataTests(unittest.TestCase):
    def test_new_listing_skips_pre_listing_year_and_keeps_available_history(self):
        daily_frame = pd.DataFrame(
            {
                "Open": [49.5], "High": [55.03], "Low": [38.11],
                "Close": [49.0], "Volume": [29_901_000], "Amount": [14_119_000_000],
            },
            index=pd.to_datetime(["2026-07-27"]),
        )
        with patch(
            "data_fetcher._fetch_a_share_year",
            side_effect=[ConnectionError("not listed"), daily_frame],
        ) as fetch_year, patch("data_fetcher._save_local_cache"):
            result = fetch_a_share_data("688825.SH", "2025-07-01", "2026-07-30")

        self.assertEqual(len(result), 1)
        self.assertEqual(fetch_year.call_count, 2)
        self.assertEqual(result.index[0], pd.Timestamp("2026-07-27"))

    def test_incomplete_a_share_history_uses_full_yahoo_fallback(self):
        partial = pd.DataFrame(
            {
                "Open": [10.0, 11.0], "High": [11.0, 12.0], "Low": [9.0, 10.0],
                "Close": [10.5, 11.5], "Volume": [1_000, 1_100], "Amount": [10_000, 12_000],
            },
            index=pd.to_datetime(["2026-01-05", "2026-08-31"]),
        )
        full_history = pd.DataFrame(
            {
                "Open": [8.0, 11.0], "High": [9.0, 12.0], "Low": [7.0, 10.0],
                "Close": [8.5, 11.5], "Volume": [900, 1_100], "Amount": [7_000, 12_000],
            },
            index=pd.to_datetime(["2025-09-01", "2026-08-31"]),
        )
        with patch("data_fetcher._fetch_a_share_year", side_effect=[pd.DataFrame(), partial]), patch(
            "data_fetcher._fetch_from_yahoo", return_value=full_history
        ) as fetch_yahoo, patch("data_fetcher._save_local_cache"):
            result = fetch_a_share_data("300308.SZ", "2025-08-31", "2026-08-31")

        self.assertEqual(fetch_yahoo.call_count, 1)
        self.assertEqual(result.index.min(), pd.Timestamp("2025-09-01"))
        self.assertEqual(result.attrs["source"], "Yahoo Finance")

    def test_ttm_profit_replaces_prior_year_comparable_cumulative_profit(self):
        periods = ["2026-03-31", "2025-12-31", "2025-03-31"]
        net_profits = ["247.62亿", "18.75亿", "-15.59亿"]

        self.assertEqual(_calculate_ttm_net_profit(periods, net_profits), 28_196_000_000)

    def test_latest_annual_cash_flow_value_uses_matching_metric(self):
        payload = {
            "title": ["科目\\时间", ["购建固定资产、无形资产和其他长期资产支付的现金"]],
            "year": [["2025", "2024"], ["8.25亿", "7.07亿"]],
        }

        self.assertEqual(
            _latest_annual_cash_flow_value(
                payload, "购建固定资产、无形资产和其他长期资产支付的现金"
            ),
            ("2025-12-31", 825_000_000),
        )

    def test_range_coverage_rejects_a_missing_first_month(self):
        partial = pd.DataFrame(
            {"Close": [10.0, 11.0]},
            index=pd.to_datetime(["2026-01-05", "2026-08-31"]),
        )

        self.assertFalse(_covers_requested_range(partial, "2025-08-31", "2026-08-31"))

    @patch("data_fetcher.yf.Ticker", _FakeTicker)
    def test_latest_intraday_session_is_normalized_for_korean_market(self):
        result = fetch_yahoo_intraday("005930.KS", "KR")

        self.assertEqual(len(result), 2)
        self.assertEqual(result.attrs["market"], "KR")
        self.assertEqual(result.attrs["trade_date"], "2026-07-22")
        self.assertEqual(result.attrs["pre_close"], 98.0)
        self.assertEqual(result.iloc[-1]["Price"], 101.5)
        self.assertEqual(result.iloc[-1]["Volume"], 30)
        self.assertAlmostEqual(result.iloc[-1]["AvgPrice"], (100.5 * 20 + 101.5 * 30) / 50)


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
