import unittest

import pandas as pd

from services.market_data import merge_intraday_daily_bar


class CurrentDailyBarTests(unittest.TestCase):
    def test_appends_latest_intraday_session_as_daily_bar(self):
        historical = pd.DataFrame(
            {
                "Open": [10.0],
                "High": [11.0],
                "Low": [9.0],
                "Close": [10.5],
                "Volume": [100.0],
            },
            index=pd.to_datetime(["2026-07-24"]),
        )
        intraday = pd.DataFrame(
            {
                "Price": [20.0, 22.0, 21.0],
                "Volume": [10.0, 20.0, 30.0],
                "Amount": [200.0, 440.0, 630.0],
            },
            index=pd.to_datetime(["2026-07-27 09:30", "2026-07-27 10:00", "2026-07-27 10:30"]),
        )
        intraday.attrs["trade_date"] = "2026-07-27"

        result = merge_intraday_daily_bar(historical, intraday, "2026-07-27")

        self.assertEqual(result.index[-1], pd.Timestamp("2026-07-27"))
        self.assertEqual(result.iloc[-1]["Open"], 20.0)
        self.assertEqual(result.iloc[-1]["High"], 22.0)
        self.assertEqual(result.iloc[-1]["Low"], 20.0)
        self.assertEqual(result.iloc[-1]["Close"], 21.0)
        self.assertEqual(result.iloc[-1]["Volume"], 60.0)
        self.assertEqual(result.iloc[-1]["Amount"], 1270.0)
        self.assertTrue(result.attrs["includes_intraday_daily_bar"])

    def test_replaces_a_stale_same_day_daily_bar(self):
        historical = pd.DataFrame(
            {"Open": [10.0], "High": [10.0], "Low": [10.0], "Close": [10.0], "Volume": [1.0]},
            index=pd.to_datetime(["2026-07-27"]),
        )
        intraday = pd.DataFrame(
            {"Price": [20.0, 21.0], "Volume": [10.0, 20.0]},
            index=pd.to_datetime(["2026-07-27 09:30", "2026-07-27 10:00"]),
        )
        intraday.attrs["trade_date"] = "2026-07-27"

        result = merge_intraday_daily_bar(historical, intraday, "2026-07-27")

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["Close"], 21.0)
        self.assertEqual(result.iloc[0]["Volume"], 30.0)


if __name__ == "__main__":
    unittest.main()
