import unittest

import pandas as pd

from visualization import plot_candlestick


class CandlestickChartTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
