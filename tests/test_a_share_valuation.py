import unittest

from data_fetcher import _calculate_ttm_net_profit


class AShareValuationTests(unittest.TestCase):
    def test_ttm_profit_replaces_prior_year_comparable_cumulative_profit(self):
        periods = ["2026-03-31", "2025-12-31", "2025-03-31"]
        net_profits = ["247.62亿", "18.75亿", "-15.59亿"]

        ttm_profit = _calculate_ttm_net_profit(periods, net_profits)

        self.assertEqual(ttm_profit, 28_196_000_000)

    def test_ttm_profit_is_unavailable_without_a_comparable_prior_period(self):
        self.assertIsNone(
            _calculate_ttm_net_profit(
                ["2026-03-31", "2025-12-31"], ["247.62亿", "18.75亿"]
            )
        )


if __name__ == "__main__":
    unittest.main()
