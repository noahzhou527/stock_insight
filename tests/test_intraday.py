import unittest
from unittest.mock import patch

import pandas as pd

from data_fetcher import fetch_yahoo_intraday


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


class YahooIntradayTests(unittest.TestCase):
    @patch("data_fetcher.yf.Ticker", _FakeTicker)
    def test_latest_session_is_normalized_for_korean_market(self):
        result = fetch_yahoo_intraday("005930.KS", "KR")

        self.assertEqual(len(result), 2)
        self.assertEqual(result.attrs["market"], "KR")
        self.assertEqual(result.attrs["trade_date"], "2026-07-22")
        self.assertEqual(result.attrs["pre_close"], 98.0)
        self.assertEqual(result.iloc[-1]["Price"], 101.5)
        self.assertEqual(result.iloc[-1]["Volume"], 30)
        self.assertAlmostEqual(result.iloc[-1]["AvgPrice"], (100.5 * 20 + 101.5 * 30) / 50)


if __name__ == "__main__":
    unittest.main()
