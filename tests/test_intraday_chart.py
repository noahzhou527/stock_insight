import unittest

import pandas as pd

from visualization import plot_intraday


class IntradayChartTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame(
            {
                "Price": [10.0, 10.2, 10.1],
                "AvgPrice": [10.0, 10.1, 10.1],
                "Volume": [1000, 1500, 1200],
                "Amount": [10_000, 15_300, 12_120],
            },
            index=pd.to_datetime(
                ["2026-08-28 09:30", "2026-08-28 10:00", "2026-08-28 10:30"]
            ),
        )
        self.frame.attrs["pre_close"] = 10.0

    def test_a_share_partial_day_keeps_full_session_axis(self):
        figure = plot_intraday(self.frame, market="CN")

        axis_range = figure.layout.xaxis.range
        self.assertEqual(pd.Timestamp(axis_range[0]), pd.Timestamp("2026-08-28 09:30"))
        self.assertEqual(pd.Timestamp(axis_range[1]), pd.Timestamp("2026-08-28 15:00"))
        self.assertEqual(figure.layout.xaxis.ticktext[2], "11:30 / 13:00")
        self.assertEqual(len(figure.layout.xaxis.rangebreaks), 1)
        self.assertFalse(figure.data[3].cliponaxis)
        self.assertFalse(figure.data[4].cliponaxis)
        self.assertEqual(figure.layout.margin.t, 115)

    def test_price_axis_is_symmetric_around_previous_close(self):
        figure = plot_intraday(self.frame, market="CN")

        lower, upper = figure.layout.yaxis.range
        self.assertAlmostEqual(10.0 - lower, upper - 10.0)
        self.assertEqual(figure.data[0].line.color, "#35a7ff")


if __name__ == "__main__":
    unittest.main()
