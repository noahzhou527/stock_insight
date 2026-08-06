import unittest

import pandas as pd

from visualization import plot_financial_report_bars


class FinancialReportChartTests(unittest.TestCase):
    def test_chart_orders_reports_oldest_to_newest_and_scales_yuan_to_yi(self):
        reports = pd.DataFrame(
            {
                "报告期": ["2025-12-31", "2024-12-31"],
                "营业总收入": ["2.00亿", "1.00亿"],
                "净利润": ["4000万", "2000万"],
            }
        )

        figure = plot_financial_report_bars(reports, "年报：营收与净利润")

        self.assertEqual([trace.name for trace in figure.data], ["营业总收入", "净利润"])
        self.assertEqual(list(figure.data[0].x), ["2024-12-31", "2025-12-31"])
        self.assertEqual(list(figure.data[0].y), [1.0, 2.0])
        self.assertEqual(list(figure.data[1].y), [0.2, 0.4])


if __name__ == "__main__":
    unittest.main()
