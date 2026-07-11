import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd

from data_fetcher import _standardize_price_frame
from services import market_overview_data as overview


class _Response:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


class _Session:
    def get(self, *_args, **_kwargs):
        return _Response({"data": {"total": 3, "diff": [{"f3": 2}, {"f3": 0}, {"f3": -1}]}})

    def close(self):
        return None


class MarketOverviewDataTests(unittest.TestCase):
    def test_price_standardization_retains_optional_amount(self):
        frame = _standardize_price_frame(
            pd.DataFrame(
                [{"Date": "2026-07-10", "Open": 1, "High": 2, "Low": 0.5, "Close": 1.5, "Volume": 100, "Amount": 150}]
            )
        )
        self.assertIn("Amount", frame.columns)
        self.assertEqual(frame.iloc[0]["Amount"], 150)

    @patch("services.market_overview_data._ths_intraday")
    @patch("services.market_overview_data._ths_daily")
    def test_cn_index_uses_latest_completed_amount_and_comparison(self, mock_daily, mock_intraday):
        today = pd.Timestamp.now(tz=ZoneInfo("Asia/Shanghai")).tz_localize(None).normalize()
        mock_daily.return_value = pd.DataFrame(
            {"Close": [100.0, 105.0], "Amount": [100_000_000.0, 120_000_000.0]},
            index=[today - pd.Timedelta(days=2), today - pd.Timedelta(days=1)],
        )
        mock_intraday.side_effect = overview.DataFetchError("unavailable", "no intraday")
        result = overview.fetch_cn_index({"name": "测试指数", "symbol": "1A0001", "display_code": "000001"})
        self.assertEqual(result["amount"], 120_000_000.0)
        self.assertEqual(result["previous_amount"], 100_000_000.0)
        self.assertEqual(result["amount_change"], 20_000_000.0)
        self.assertEqual(result["amount_change_pct"], 20.0)

    @patch("services.market_overview_data.requests.Session", return_value=_Session())
    def test_cn_breadth_counts_all_returned_rows(self, _mock_session):
        breadth = overview.fetch_cn_market_breadth()
        self.assertEqual(breadth["up"], 3)
        self.assertEqual(breadth["flat"], 3)
        self.assertEqual(breadth["down"], 3)
        self.assertEqual(breadth["total"], 9)

    @patch("services.market_overview_data._screen_count", side_effect=[100, 42, 37])
    def test_us_breadth_derives_flat_count(self, _screen_count):
        breadth = overview.fetch_us_market_breadth()
        self.assertEqual(breadth, {"up": 42, "down": 37, "flat": 21, "total": 100, "source": "Yahoo 可筛选的美国上市普通股"})

    @patch("services.market_overview_data.is_us_trading_session", return_value=False)
    @patch("services.market_overview_data._us_history")
    def test_us_index_intraday_keeps_only_latest_session(self, mock_history, _mock_session):
        daily = pd.DataFrame(
            {"Close": [52_000.0, 52_500.0]},
            index=pd.to_datetime(["2026-07-09", "2026-07-10"]),
        )
        intraday = pd.DataFrame(
            {"Close": [52_100.0, 52_200.0, 52_450.0, 52_500.0]},
            index=pd.to_datetime(
                [
                    "2026-07-09 09:30-04:00",
                    "2026-07-09 16:00-04:00",
                    "2026-07-10 09:30-04:00",
                    "2026-07-10 16:00-04:00",
                ]
            ),
        )
        mock_history.side_effect = [daily, intraday]
        result = overview.fetch_us_index({"name": "道琼斯", "symbol": "^DJI"})
        dates = {timestamp.date() for timestamp in result["intraday"].index}
        self.assertEqual(dates, {datetime(2026, 7, 10).date()})
        self.assertEqual(len(result["intraday"]), 2)


if __name__ == "__main__":
    unittest.main()
