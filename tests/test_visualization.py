import unittest

import pandas as pd

from visualization import plot_candlestick, plot_intraday


class CandlestickChartTests(unittest.TestCase):
    def test_short_history_occupies_left_half_without_padding_prices(self):
        frame = pd.DataFrame(
            {"Open": [10.] * 50, "High": [12.] * 50, "Low": [9.] * 50,
             "Close": [11.] * 50, "Volume": [100.] * 50},
            index=pd.bdate_range("2026-07-01", periods=50),
        )
        figure = plot_candlestick(frame, display_sessions=100)
        self.assertEqual(len(figure.data[0].x), 50)
        self.assertEqual(figure.layout.xaxis.range, (-0.5, 99.5))
        self.assertEqual(figure.layout.xaxis2.range, (-0.5, 99.5))
        self.assertEqual(len(figure.layout.xaxis.categoryarray), 50)
        self.assertEqual(figure.layout.xaxis.categoryarray[0], "2026-07-01")

    def test_marks_selected_range_high_and_low(self):
        frame = pd.DataFrame(
            {
                "Open": [10.0, 12.0, 9.0],
                "High": [13.0, 15.5, 11.0],
                "Low": [8.5, 11.0, 7.25],
                "Close": [12.0, 13.0, 10.0],
                "Volume": [100, 120, 90],
            },
            index=pd.to_datetime(["2026-08-03", "2026-08-04", "2026-08-05"]),
        )

        figure = plot_candlestick(frame, market="CN", currency="CNY")
        annotations = list(figure.layout.annotations)

        self.assertEqual(len(annotations), 2)
        self.assertEqual(
            {annotation.text for annotation in annotations},
            {"<b>最高</b> 15.50", "<b>最低</b> 7.25"},
        )
        self.assertTrue(all(annotation.font.color == "#f8fafc" for annotation in annotations))
        high_annotation = next(annotation for annotation in annotations if "最高" in annotation.text)
        low_annotation = next(annotation for annotation in annotations if "最低" in annotation.text)
        self.assertGreater(high_annotation.ay, frame["High"].max())
        self.assertLess(low_annotation.ay, frame["Low"].min())


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

    def test_high_low_markers_tone_follows_pre_close_side(self):
        # All prices at/above pre-close: both extremes render in the up color.
        figure = plot_intraday(self.frame, market="CN")
        self.assertEqual(figure.data[3].marker.color, "#e53935")
        self.assertEqual(figure.data[3].textfont.color, "#e53935")
        self.assertEqual(figure.data[4].marker.color, "#e53935")
        self.assertEqual(figure.data[4].textfont.color, "#e53935")

        # All prices below pre-close: both extremes render in the down color.
        below = self.frame.copy()
        below["Price"] = below["Price"] - 1.0
        below.attrs["pre_close"] = 10.0
        figure = plot_intraday(below, market="CN")
        self.assertEqual(figure.data[3].marker.color, "#1e9d55")
        self.assertEqual(figure.data[4].marker.color, "#1e9d55")

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
