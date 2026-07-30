import unittest
from unittest.mock import patch

import pandas as pd

from data_fetcher import fetch_a_share_data


class AShareHistoryTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
