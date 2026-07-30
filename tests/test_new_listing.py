import unittest

import pandas as pd

from new_listing import (
    get_new_listing_state,
    is_new_listing_history,
    pad_new_listing_chart,
)


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

    def test_new_listing_chart_matches_the_selected_date_range_slot_count(self):
        history = pd.DataFrame(
            {"Open": [49.5, 45.22, 46.5, 52.2], "Close": [49.0, 47.0, 52.95, 52.87]},
            index=pd.to_datetime(["2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30"]),
        )

        display_start, display_end = "2026-07-01", "2026-07-30"
        chart_history = pad_new_listing_chart(
            history, is_new_listing=True, display_start=display_start, display_end=display_end
        )

        self.assertEqual(len(chart_history), len(pd.bdate_range(display_start, display_end)))
        self.assertEqual(chart_history.loc[pd.Timestamp("2026-07-27"), "Close"], 49.0)
        self.assertEqual(chart_history["Close"].notna().sum(), 4)
        self.assertEqual(chart_history.index[0], pd.Timestamp("2026-07-27"))

    def test_mature_stock_keeps_its_selected_chart_range(self):
        history = pd.DataFrame(
            {"Close": range(10)}, index=pd.bdate_range("2026-01-01", periods=10)
        )

        self.assertFalse(is_new_listing_history(history, "2025-12-29"))
        self.assertEqual(
            len(pad_new_listing_chart(history, is_new_listing=False, display_start="2025-12-29", display_end="2026-01-14")),
            10,
        )


if __name__ == "__main__":
    unittest.main()
