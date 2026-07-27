import unittest

import pandas as pd

from new_listing import get_new_listing_state, pad_single_daily_bar_chart


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

    def test_mature_history_enables_all_indicators(self):
        state = get_new_listing_state(pd.DataFrame({"Close": range(30)}), rsi_period=14)

        self.assertEqual(state["previous_close"], 28.0)
        self.assertTrue(all(state[key] for key in ("show_rows_slider", "trend_ready", "rsi_ready", "macd_ready", "volatility_ready")))

    def test_first_day_chart_reserves_a_year_of_blank_daily_slots(self):
        history = pd.DataFrame({"Open": [49.5], "Close": [49.0]}, index=pd.to_datetime(["2026-07-27"]))

        chart_history = pad_single_daily_bar_chart(history)

        self.assertEqual(len(chart_history), 252)
        self.assertEqual(chart_history.loc[pd.Timestamp("2026-07-27"), "Close"], 49.0)
        self.assertEqual(chart_history["Close"].notna().sum(), 1)
        self.assertEqual(chart_history.index[0], pd.Timestamp("2026-07-27"))


if __name__ == "__main__":
    unittest.main()
