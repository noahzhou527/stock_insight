import pandas as pd
import streamlit as st

from data_fetcher import DataFetchError
from formatters import format_financial_report_table
from services.market_data import load_financial_reports
from visualization import plot_financial_report_bars


def render_financial_reports(
    ticker: str,
    market: str,
    display_market: str,
    krw_usd_rate: float,
) -> None:
    st.subheader("年度与季度财务报告")
    try:
            financial_reports = load_financial_reports(ticker, market, cache_version=2)
            annual_reports = financial_reports[
                financial_reports["报告类型"] == "年报"
            ].head(4)
            quarter_reports = financial_reports[
                financial_reports["报告类型"] != "年报"
            ].head(4)
            quarter_chart_reports = quarter_reports
            if market == "CN" and not quarter_reports.empty:
                quarter_dates = pd.to_datetime(quarter_reports["报告期"])
                annual_fill_reports = financial_reports[
                    (financial_reports["报告类型"] == "年报")
                    & pd.to_datetime(financial_reports["报告期"]).between(
                        quarter_dates.min(), quarter_dates.max()
                    )
                ]
                quarter_chart_reports = (
                    pd.concat([quarter_reports, annual_fill_reports], ignore_index=True)
                    .drop_duplicates(subset=["报告期"], keep="first")
                    .sort_values("报告期", ascending=False)
                )
    
            source_note = "；季报指标为报告期累计口径。" if market == "CN" else "；金额按报告币种展示。"
            if market == "KR" and display_market == "US":
                source_note = f"；金额与每股收益按参考汇率换算为美元（1 美元 = {1 / krw_usd_rate:,.2f} 韩元）。"
            st.caption(f"数据来源：{financial_reports.attrs.get('source', '—')}{source_note}")
    
            if market == "CN" and (not annual_reports.empty or not quarter_reports.empty):
                st.markdown("#### 财报趋势")
                annual_chart_column, quarter_chart_column = st.columns(2)
                with annual_chart_column:
                    if not annual_reports.empty:
                        st.plotly_chart(
                            plot_financial_report_bars(annual_reports, "年报：营收与净利润"),
                            width="stretch",
                            key=f"financial-annual-bars:{ticker}",
                            config={"displayModeBar": False},
                        )
                with quarter_chart_column:
                    if not quarter_reports.empty:
                        st.plotly_chart(
                            plot_financial_report_bars(quarter_chart_reports, "季报趋势（年报补齐第四季度）"),
                            width="stretch",
                            key=f"financial-quarter-bars:{ticker}",
                            config={"displayModeBar": False},
                        )
                        if len(quarter_chart_reports) > len(quarter_reports):
                            st.caption("季度图以年报补齐缺失的第四季度；下方季度表不受影响。")
    
            annual_heading = f"近{len(annual_reports)}个财年" if not annual_reports.empty else "财年报告"
            st.markdown(f"#### {annual_heading}")
            if annual_reports.empty:
                st.info("暂未读取到可展示的年报。")
            else:
                st.table(
                    format_financial_report_table(annual_reports, display_market, krw_usd_rate),
                    width="stretch",
                    hide_index=True,
                )
    
            quarter_heading = f"最新{len(quarter_reports)}个季度" if not quarter_reports.empty else "季度报告"
            st.markdown(f"#### {quarter_heading}")
            if quarter_reports.empty:
                st.info("暂未读取到可展示的季度报告。")
            else:
                st.table(
                    format_financial_report_table(quarter_reports, display_market, krw_usd_rate),
                    width="stretch",
                    hide_index=True,
                )
    except DataFetchError as error:
        st.warning(str(error))
